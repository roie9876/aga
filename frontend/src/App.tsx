import { useState } from 'react';
import { 
  CheckCircle2, 
  Sparkles, 
  Loader2, 
  History, 
  FileText,
  AlertCircle,
  TrendingUp,
  Shield,
  Plus
} from 'lucide-react';
import { DecompositionUpload } from './components/DecompositionUpload';
import { DecompositionReview } from './components/DecompositionReview';
import { RequirementItem } from './components/RequirementItem';
import { Button, Card, StatCard, Badge, ProgressBar, EmptyState, FloatingActionButton } from './components/ui';
import { StepIndicator } from './components/ValidationComponents';

type WorkflowStage = 'upload' | 'decomposition_review' | 'validation' | 'results' | 'history';

function App() {
  const [stage, setStage] = useState<WorkflowStage>('upload');
  const [decompositionId, setDecompositionId] = useState<string | null>(null);
  const [projectId] = useState<string>('demo-project-001');
  const [validationProgress, setValidationProgress] = useState<{
    total: number;
    current: number;
    currentSegment: string;
  } | null>(null);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [validationHistory, setValidationHistory] = useState<any[]>([]);
  
  const handleDecompositionComplete = (decompId: string) => {
    setDecompositionId(decompId);
    setStage('decomposition_review');
  };
  
  const handleApprovalComplete = async (approvedSegmentIds: string[]) => {
    setStage('validation');
    setValidationProgress({
      total: approvedSegmentIds.length,
      current: 0,
      currentSegment: 'מתחיל בדיקה...'
    });
    
    try {
      const response = await fetch('/api/v1/segments/validate-segments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decomposition_id: decompositionId,
          approved_segment_ids: approvedSegmentIds,
        }),
      });
      
      if (!response.ok) throw new Error('Validation failed');
      
      const result = await response.json();
      
      const decompResponse = await fetch(`/api/v1/decomposition/${decompositionId}`);
      if (!decompResponse.ok) throw new Error('Failed to fetch decomposition data');
      const decompData = await decompResponse.json();
      
      const enrichedResult = {
        ...result,
        segments: result.analyzed_segments?.map((analysis: any) => {
          const segment = decompData.segments?.find(
            (s: any) => s.segment_id === analysis.segment_id
          );
          return {
            ...analysis,
            blob_url: segment?.blob_url,
            thumbnail_url: segment?.thumbnail_url,
            type: segment?.type,
            description: segment?.description
          };
        }) || []
      };
      
      setValidationResult(enrichedResult);
      setStage('results');
      
    } catch (error) {
      console.error('Validation error:', error);
      alert('שגיאה בבדיקת הסגמנטים');
      setStage('decomposition_review');
    }
  };
  
  const loadHistory = async () => {
    try {
      const response = await fetch(`/api/v1/projects/${projectId}/validations`);
      if (!response.ok) throw new Error('Failed to load history');
      const data = await response.json();
      const latest = (data.validations || []).slice(0, 10);
      setValidationHistory(latest);
      setStage('history');
    } catch (error) {
      console.error('History error:', error);
      alert('שגיאה בטעינת היסטוריה');
    }
  };
  
  const resetWorkflow = () => {
    setStage('upload');
    setDecompositionId(null);
    setValidationResult(null);
    setValidationProgress(null);
  };

  const steps = [
    { number: 1, title: 'העלאה', description: 'העלאת קובץ התכנית' },
    { number: 2, title: 'סגמנטציה', description: 'זיהוי חלקי התכנית' },
    { number: 3, title: 'אישור', description: 'בחירת סגמנטים' },
    { number: 4, title: 'בדיקה', description: 'וולידציה מול תקנים' },
  ];

  const currentStepNumber = 
    stage === 'upload' ? 1 :
    stage === 'decomposition_review' ? 3 :
    stage === 'validation' ? 4 :
    stage === 'results' ? 4 : 1;

  return (
    <div className="min-h-screen bg-background text-text-primary font-sans antialiased" dir="rtl">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center shadow-sm">
                <Shield className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-text-primary tracking-tight">בדיקת ממ״ד</h1>
                <p className="text-sm text-text-muted">מערכת וולידציה אוטומטית</p>
              </div>
            </div>
            
            {stage !== 'history' && (
              <Button 
                variant="ghost" 
                size="sm"
                icon={<History className="w-4 h-4" />}
                onClick={loadHistory}
              >
                היסטוריה
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        {/* Step Indicator - Show only in workflow stages */}
        {stage !== 'history' && (
          <StepIndicator currentStep={currentStepNumber} steps={steps} />
        )}

        {/* Upload Stage */}
        {stage === 'upload' && (
          <div className="grid gap-8 lg:grid-cols-3 items-start">
            <div className="lg:col-span-2 space-y-6">
              <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary to-primary-hover text-white p-10 shadow-xl">
                <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.3)_0,_transparent_45%)]" />
                <div className="relative flex flex-col gap-5">
                  <div className="inline-flex items-center gap-2 bg-white/10 border border-white/20 text-white rounded-full px-3 py-1 text-sm w-fit backdrop-blur-sm">
                    <Sparkles className="w-4 h-4" />
                    <span className="font-medium">חוויית SaaS מודרנית</span>
                  </div>
                  <div>
                    <h2 className="text-3xl font-bold leading-tight tracking-tight">העלה תכנית לבדיקה</h2>
                    <p className="text-white/90 mt-3 max-w-2xl text-lg leading-relaxed">
                      המערכת תנתח את התכנית, תזהה סגמנטים ותבצע וולידציה חכמה מול תקני ממ"ד בעזרת GPT-5.1
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-3 pt-2">
                    <Badge variant="info">זיהוי סגמנטים אוטומטי</Badge>
                    <Badge variant="success">כיסוי מלא של 16 תקנים</Badge>
                    <Badge variant="neutral">תוצאות בזמן אמת</Badge>
                  </div>
                </div>
              </div>

              <Card padding="lg" className="shadow-lg shadow-primary/5 border-border">
                <DecompositionUpload 
                  projectId={projectId}
                  onDecompositionComplete={handleDecompositionComplete}
                />
              </Card>

              <Card padding="md" className="bg-background border-dashed border-border">
                <div className="flex flex-wrap items-center gap-4">
                  <div className="rounded-lg bg-white px-4 py-3 shadow-sm border border-border">
                    <p className="text-xs text-text-muted font-medium mb-1">שלבי עבודה</p>
                    <p className="font-semibold text-text-primary">העלאה → אישור → בדיקה → תוצאות</p>
                  </div>
                  <div className="text-sm text-text-muted leading-relaxed max-w-xl">
                    שמור על סדר עבודה: העלה קובץ, אשר סגמנטים, הרץ בדיקות וקבל דוח מפורט עם כיסוי תקנים.
                  </div>
                </div>
              </Card>
            </div>

            <div className="space-y-4">
              <Card padding="md" className="bg-white/80 backdrop-blur border-border">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="text-sm text-text-muted font-medium">תמיכה מלאה</p>
                    <p className="text-lg font-semibold text-text-primary">מוכנים להתחיל</p>
                  </div>
                  <Shield className="w-6 h-6 text-primary" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg bg-primary/5 border border-primary/10 p-3">
                    <p className="text-xs text-text-muted font-medium">תקנים</p>
                    <p className="font-semibold text-text-primary">16</p>
                  </div>
                  <div className="rounded-lg bg-background border border-border p-3">
                    <p className="text-xs text-text-muted font-medium">קבצים נתמכים</p>
                    <p className="font-semibold text-text-primary">PDF · DWF · PNG</p>
                  </div>
                </div>
              </Card>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-4">
                <Card padding="md" className="text-left hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Sparkles className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-text-primary">AI מתקדם</p>
                      <p className="text-xs text-text-muted mt-1">GPT-5.1 Reasoning</p>
                    </div>
                  </div>
                </Card>
                <Card padding="md" className="text-left hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center flex-shrink-0">
                      <CheckCircle2 className="w-5 h-5 text-success" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-text-primary">16 בדיקות</p>
                      <p className="text-xs text-text-muted mt-1">כל תקני ממ"ד</p>
                    </div>
                  </div>
                </Card>
                <Card padding="md" className="text-left hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <TrendingUp className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-text-primary">דוח מפורט</p>
                      <p className="text-xs text-text-muted mt-1">כיסוי דרישות</p>
                    </div>
                  </div>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* Decomposition Review Stage */}
        {stage === 'decomposition_review' && decompositionId && (
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-10">
              <h2 className="text-3xl font-bold text-text-primary mb-3 tracking-tight">
                בחר סגמנטים לבדיקה
              </h2>
              <p className="text-text-muted text-lg max-w-2xl mx-auto">
                המערכת זיהתה את החלקים הבאים בתכנית. אשר את הסגמנטים שברצונך לבדוק
              </p>
            </div>
            
            <DecompositionReview 
              decompositionId={decompositionId}
              onApprove={handleApprovalComplete}
              onReject={() => setStage('upload')}
            />
            
            <div className="mt-10 text-center">
              <Button 
                variant="ghost" 
                onClick={resetWorkflow}
              >
                חזור להעלאה
              </Button>
            </div>
          </div>
        )}

        {/* Validation Progress Stage */}
        {stage === 'validation' && validationProgress && (
          <div className="max-w-2xl mx-auto">
            <Card padding="lg" className="shadow-lg">
              <div className="text-center mb-10">
                <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-6">
                  <Loader2 className="w-10 h-10 text-primary animate-spin" />
                </div>
                <h2 className="text-2xl font-bold text-text-primary mb-2">
                  מריץ בדיקות...
                </h2>
                <p className="text-text-muted">
                  {validationProgress.currentSegment}
                </p>
              </div>
              
              <div className="space-y-4 max-w-md mx-auto">
                <ProgressBar 
                  value={validationProgress.current} 
                  max={validationProgress.total}
                  color="violet"
                  size="lg"
                  showLabel
                />
                <p className="text-sm text-center text-text-muted">
                  {validationProgress.current} מתוך {validationProgress.total} סגמנטים
                </p>
              </div>
            </Card>
          </div>
        )}

        {/* Results Stage */}
        {stage === 'results' && validationResult && (
          <div className="max-w-7xl mx-auto space-y-10">
            {/* Success Header */}
            <Card padding="lg" className="bg-gradient-to-r from-success/5 via-white to-primary/5 border-border shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
                <div className="flex items-center gap-5">
                  <div className="w-16 h-16 bg-success/10 rounded-2xl flex items-center justify-center border border-success/20">
                    <CheckCircle2 className="w-8 h-8 text-success" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold text-text-primary mb-1">הבדיקות הושלמו!</h2>
                    <p className="text-text-muted">ניתוח GPT-5.1 הושלם בהצלחה</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Badge variant="success">עברו {validationResult.passed || 0} בדיקות</Badge>
                  <Badge variant="info">{validationResult.total_segments} סגמנטים נותחו</Badge>
                  <Badge variant="warning">{validationResult.warnings || 0} אזהרות</Badge>
                </div>
              </div>
            </Card>

            <div className="grid gap-8 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-6">
                {/* Coverage Report */}
                {validationResult.coverage && (
                  <Card padding="lg" className="shadow-md border-border">
                    <h3 className="text-xl font-bold text-text-primary mb-6">
                      כיסוי דרישות ממ״ד
                    </h3>
                    
                    {/* Coverage Statistics */}
                    <div className="bg-background rounded-xl p-6 mb-8 border border-border">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                        <div className="bg-white rounded-lg p-4 shadow-sm border border-border text-center">
                          <div className="text-3xl font-bold text-primary">
                            {validationResult.coverage.statistics.coverage_percentage}%
                          </div>
                          <div className="text-xs text-text-muted mt-1 font-medium">כיסוי דרישות</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 shadow-sm border border-border text-center">
                          <div className="text-3xl font-bold text-success">
                            {validationResult.coverage.statistics.passed}
                          </div>
                          <div className="text-xs text-text-muted mt-1 font-medium">עברו בדיקה</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 shadow-sm border border-border text-center">
                          <div className="text-3xl font-bold text-error">
                            {validationResult.coverage.statistics.failed}
                          </div>
                          <div className="text-xs text-text-muted mt-1 font-medium">נכשלו</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 shadow-sm border border-border text-center">
                          <div className="text-3xl font-bold text-text-muted">
                            {validationResult.coverage.statistics.not_checked}
                          </div>
                          <div className="text-xs text-text-muted mt-1 font-medium">לא נבדקו</div>
                        </div>
                      </div>
                      
                      <ProgressBar 
                        value={validationResult.coverage.statistics.coverage_percentage}
                        max={100}
                        color="violet"
                        size="lg"
                      />
                      <p className="text-center text-sm text-text-muted mt-3">
                        {validationResult.coverage.statistics.checked} מתוך {validationResult.coverage.statistics.total_requirements} דרישות נבדקו
                      </p>
                    </div>
                    
                    {/* Requirements by Category */}
                    <div className="space-y-4 mb-8">
                      <h4 className="text-lg font-semibold text-text-primary">דרישות לפי קטגוריה</h4>
                      {Object.entries(validationResult.coverage.by_category || {}).map(([category, requirements]: [string, any]) => (
                        <div key={category} className="border border-border rounded-xl overflow-hidden">
                          <div className="bg-gray-50 px-5 py-3 border-b border-border">
                            <h5 className="font-semibold text-text-primary">{category}</h5>
                          </div>
                          <div className="divide-y divide-border">
                            {requirements.map((req: any) => (
                              <RequirementItem key={req.requirement_id} req={req} />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    {/* Missing Segments */}
                    {validationResult.coverage.missing_segments_needed?.length > 0 && (
                      <div className="bg-warning/5 rounded-xl p-6 border border-warning/20">
                        <div className="flex items-start gap-3 mb-4">
                          <AlertCircle className="w-5 h-5 text-warning mt-0.5" />
                          <div>
                            <h4 className="font-semibold text-warning mb-1">
                              נדרש להוספה להשלמת הבדיקה
                            </h4>
                            <p className="text-sm text-warning/80">
                              הדרישות הבאות לא נבדקו מכיוון שלא נמצאו סגמנטים רלוונטיים
                            </p>
                          </div>
                        </div>
                        <div className="space-y-3">
                          {validationResult.coverage.missing_segments_needed.map((missing: any, i: number) => (
                            <div 
                              key={i}
                              className="bg-white rounded-lg p-4 border border-warning/20 shadow-sm"
                            >
                              <div className="flex items-start gap-3">
                                <Badge variant="warning" size="sm">
                                  {missing.requirement_id}
                                </Badge>
                                <div className="flex-1">
                                  <p className="text-sm text-text-primary font-medium mb-1">
                                    {missing.description}
                                  </p>
                                  <p className="text-xs text-text-muted">
                                    <span className="font-semibold">דרוש:</span> {missing.needed_segment_type}
                                  </p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </Card>
                )}
              </div>

              <div className="space-y-4">
                <Card padding="md" className="space-y-4 border-border">
                  <h4 className="text-lg font-semibold text-text-primary">סטטוס כללי</h4>
                  <div className="grid grid-cols-1 gap-3">
                    <StatCard 
                      label="סגמנטים נותחו"
                      value={validationResult.total_segments}
                      icon={<FileText className="w-5 h-5" />}
                      color="blue"
                    />
                    <StatCard 
                      label="הושלמו בהצלחה"
                      value={validationResult.passed || 0}
                      icon={<CheckCircle2 className="w-5 h-5" />}
                      color="green"
                    />
                    <StatCard 
                      label="אזהרות"
                      value={validationResult.warnings || 0}
                      icon={<AlertCircle className="w-5 h-5" />}
                      color="amber"
                    />
                  </div>
                </Card>

                <Card padding="md" className="bg-background border-border">
                  <p className="text-sm text-text-muted">
                    <span className="font-semibold text-text-primary">מזהה בדיקה:</span>
                    <span className="ml-2 font-mono text-xs">{validationResult.validation_id}</span>
                  </p>
                </Card>

                <Card padding="md" className="space-y-3 border-border">
                  <h4 className="text-lg font-semibold text-text-primary">פעולות מהירות</h4>
                  <Button
                    variant="secondary"
                    size="md"
                    icon={<History className="w-5 h-5" />}
                    onClick={loadHistory}
                    fullWidth
                  >
                    היסטוריה
                  </Button>
                  <Button
                    variant="primary"
                    size="md"
                    icon={<Plus className="w-5 h-5" />}
                    onClick={resetWorkflow}
                    fullWidth
                  >
                    בדיקה חדשה
                  </Button>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* History Stage */}
        {stage === 'history' && (
          <div className="max-w-6xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <div>
                <h2 className="text-3xl font-bold text-text-primary mb-2 tracking-tight">
                  היסטוריית בדיקות
                </h2>
                <p className="text-text-muted">
                  כל הבדיקות שבוצעו עד כה
                </p>
              </div>
              <Button
                variant="primary"
                icon={<Plus className="w-5 h-5" />}
                onClick={resetWorkflow}
              >
                בדיקה חדשה
              </Button>
            </div>
            
            {validationHistory.length === 0 ? (
              <Card padding="lg">
                <EmptyState
                  icon={<History className="w-8 h-8" />}
                  title="אין בדיקות קודמות"
                  description="התחל בדיקה חדשה כדי לראות אותה כאן"
                  action={{
                    label: 'התחל בדיקה',
                    onClick: resetWorkflow
                  }}
                />
              </Card>
            ) : (
              <div className="space-y-4">
                {validationHistory.map((validation: any, idx: number) => (
                  <Card key={idx} hover padding="md">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center">
                          <FileText className="w-6 h-6 text-primary" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-text-primary">
                            {validation.plan_name || 'תכנית ללא שם'}
                          </h3>
                          <p className="text-sm text-text-muted">
                            {new Date(validation.created_at).toLocaleDateString('he-IL', {
                              year: 'numeric',
                              month: 'long',
                              day: 'numeric'
                            })}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge 
                          variant={
                            validation.status === 'pass' ? 'success' :
                            validation.status === 'fail' ? 'error' : 'warning'
                          }
                        >
                          {validation.status === 'pass' ? 'עבר' :
                           validation.status === 'fail' ? 'נכשל' : 'לבדיקה'}
                        </Badge>
                        <span className="text-sm text-text-muted">
                          {validation.total_checks || 0} בדיקות
                        </span>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Floating Action Button - Show in results stage */}
      {stage === 'results' && (
        <FloatingActionButton
          onClick={resetWorkflow}
          icon={<Plus className="w-6 h-6" />}
          label="בדיקה חדשה"
        />
      )}
    </div>
  );
}

export default App;
