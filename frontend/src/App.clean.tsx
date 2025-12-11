import { useState } from 'react';
import { Upload, CheckCircle, Sparkles, ArrowRight, Loader2, Zap } from 'lucide-react';
import type { PlanDecomposition } from './types';
import DecompositionUpload from './components/DecompositionUpload';
import DecompositionReview from './components/DecompositionReview';

// Workflow stages
type WorkflowStage = 'upload' | 'decomposition_review' | 'validation' | 'results';

function App() {
  const [stage, setStage] = useState<WorkflowStage>('upload');
  const [decompositionId, setDecompositionId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string>('demo-project-001');
  
  // Handle decomposition complete
  const handleDecompositionComplete = (decompId: string) => {
    setDecompositionId(decompId);
    setStage('decomposition_review');
  };
  
  // Handle decomposition approved
  const handleApprovalComplete = async () => {
    setStage('validation');
    // TODO: Start validation on approved segments
    // For now, just show completion message
    setTimeout(() => {
      setStage('results');
    }, 2000);
  };
  
  // Handle rejection - go back to upload
  const handleRejection = () => {
    setStage('upload');
    setDecompositionId(null);
  };
  
  // Render stage indicator
  const renderStageIndicator = () => {
    const stages = [
      { id: 'upload', label: 'העלאה', icon: Upload },
      { id: 'decomposition_review', label: 'סקירת פירוק', icon: Sparkles },
      { id: 'validation', label: 'בדיקה', icon: Zap },
      { id: 'results', label: 'תוצאות', icon: CheckCircle }
    ];
    
    const currentIndex = stages.findIndex(s => s.id === stage);
    
    return (
      <div className="flex items-center justify-center gap-2 mb-8">
        {stages.map((s, index) => {
          const Icon = s.icon;
          const isActive = index === currentIndex;
          const isCompleted = index < currentIndex;
          
          return (
            <div key={s.id} className="flex items-center">
              <div className={`
                flex items-center gap-2 px-4 py-2 rounded-lg transition-all
                ${isActive ? 'bg-blue-500 text-white' : ''}
                ${isCompleted ? 'bg-green-500 text-white' : ''}
                ${!isActive && !isCompleted ? 'bg-gray-200 text-gray-500' : ''}
              `}>
                <Icon className="w-5 h-5" />
                <span className="text-sm font-medium">{s.label}</span>
              </div>
              {index < stages.length - 1 && (
                <ArrowRight className="w-5 h-5 mx-2 text-gray-400" />
              )}
            </div>
          );
        })}
      </div>
    );
  };
  
  // Render based on current stage
  const renderStageContent = () => {
    switch (stage) {
      case 'upload':
        return (
          <DecompositionUpload
            projectId={projectId}
            onProjectIdChange={setProjectId}
            onDecompositionComplete={handleDecompositionComplete}
          />
        );
      
      case 'decomposition_review':
        if (!decompositionId) return null;
        return (
          <DecompositionReview
            decompositionId={decompositionId}
            onApprove={handleApprovalComplete}
            onReject={handleRejection}
          />
        );
      
      case 'validation':
        return (
          <div className="text-center py-12">
            <Loader2 className="w-16 h-16 mx-auto mb-4 text-blue-500 animate-spin" />
            <h2 className="text-2xl font-bold mb-2">מריץ בדיקות...</h2>
            <p className="text-gray-600">מבצע בדיקות על הסגמנטים שאושרו</p>
          </div>
        );
      
      case 'results':
        return (
          <div className="text-center py-12">
            <CheckCircle className="w-16 h-16 mx-auto mb-4 text-green-500" />
            <h2 className="text-2xl font-bold mb-2">הבדיקות הושלמו!</h2>
            <p className="text-gray-600">כל הבדיקות עברו בהצלחה</p>
            <button
              onClick={() => {
                setStage('upload');
                setDecompositionId(null);
              }}
              className="mt-6 px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
            >
              בדיקה חדשה
            </button>
          </div>
        );
      
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-indigo-100" dir="rtl">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <Sparkles className="w-12 h-12 text-purple-600" />
            <h1 className="text-5xl font-black bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
              בודק ממ"ד GPT-5.1
            </h1>
          </div>
          <p className="text-xl text-gray-600 font-medium">
            מערכת אינטליגנטית לבדיקת תוכניות אדריכליות של ממ"ד
          </p>
        </div>
        
        {/* Stage Indicator */}
        {renderStageIndicator()}
        
        {/* Main Content */}
        <div className="max-w-6xl mx-auto">
          {renderStageContent()}
        </div>
      </div>
    </div>
  );
}

export default App;
