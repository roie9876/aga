import { useState } from 'react';
import { Upload, CheckCircle, XCircle, AlertTriangle, FileText, Loader2, Sparkles, Zap } from 'lucide-react';
import type { ValidationResponse } from './types';

const API_BASE_URL = 'http://localhost:8000';

// Demo plans with metadata
const DEMO_PLANS = [
  {
    name: 'demo_plan_perfect.png',
    title: 'תוכנית מושלמת ✅',
    description: 'כל 20 הבדיקות עוברות',
    icon: '🎉',
    color: 'from-green-400 to-emerald-500',
    status: 'perfect'
  },
  {
    name: 'demo_plan_thin_walls.png',
    title: 'קירות דקים מדי ❌',
    description: 'בעיית עובי קירות',
    icon: '🧱',
    color: 'from-red-400 to-rose-500',
    status: 'fail'
  },
  {
    name: 'demo_plan_low_height.png',
    title: 'גובה נמוך מדי ❌',
    description: 'בעיית גובה חדר',
    icon: '📏',
    color: 'from-orange-400 to-amber-500',
    status: 'fail'
  },
  {
    name: 'demo_plan_door_spacing.png',
    title: 'מרחק דלת לא תקין ❌',
    description: 'בעיית מרחקי דלת',
    icon: '🚪',
    color: 'from-yellow-400 to-orange-500',
    status: 'fail'
  },
];

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string>('demo-project-001');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedDemo, setSelectedDemo] = useState<string | null>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setResult(null);
      setError(null);
      
      // Create preview
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result as string);
      };
      reader.readAsDataURL(selectedFile);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && (droppedFile.type.startsWith('image/') || droppedFile.type === 'application/pdf')) {
      setFile(droppedFile);
      setResult(null);
      setError(null);
      
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result as string);
      };
      reader.readAsDataURL(droppedFile);
    }
  };

  const handleValidate = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('project_id', projectId);

      const response = await fetch(`${API_BASE_URL}/api/v1/validate`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Validation failed');
      }

      const uploadResponse = await response.json();
      const validationId = uploadResponse.validation_id;

      // Fetch the full validation results
      const resultsResponse = await fetch(`${API_BASE_URL}/api/v1/results/${validationId}`);
      
      if (!resultsResponse.ok) {
        throw new Error('Failed to fetch validation results');
      }

      const data: ValidationResponse = await resultsResponse.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (passed: boolean) => {
    return passed ? (
      <CheckCircle className="w-5 h-5 text-green-500" />
    ) : (
      <XCircle className="w-5 h-5 text-red-500" />
    );
  };

  const getOverallStatusColor = (status: string) => {
    switch (status) {
      case 'passed':
        return 'bg-green-100 text-green-800 border-green-300';
      case 'failed':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'warning':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const loadDemoFile = async (demoName: string) => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);
      setSelectedDemo(demoName);
      
      const response = await fetch(`/demo/${demoName}`);
      if (!response.ok) {
        throw new Error(`Failed to load demo file: ${response.statusText}`);
      }
      const blob = await response.blob();
      const demoFile = new File([blob], demoName, { type: 'image/png' });
      
      setFile(demoFile);
      
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result as string);
      };
      reader.readAsDataURL(demoFile);
      
      // Auto-validate
      setTimeout(() => {
        const formData = new FormData();
        formData.append('file', demoFile);
        formData.append('project_id', projectId);

        fetch(`${API_BASE_URL}/api/v1/validate`, {
          method: 'POST',
          body: formData,
        })
          .then(async res => {
            if (!res.ok) {
              const errorData = await res.json().catch(() => ({ detail: 'Server error' }));
              throw new Error(errorData.detail || `Server error: ${res.status}`);
            }
            return res.json();
          })
          .then(uploadResponse => {
            const validationId = uploadResponse.validation_id;
            return fetch(`${API_BASE_URL}/api/v1/results/${validationId}`);
          })
          .then(res => res.json())
          .then(data => {
            setResult(data);
            setLoading(false);
          })
          .catch(err => {
            setError(err.message || 'שגיאה בתקשורת עם השרת');
            setLoading(false);
          });
      }, 500);
    } catch (err) {
      setError('Failed to load demo file');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-900 via-purple-900 to-pink-800 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header with Animation */}
        <div className="text-center mb-12 animate-fade-in">
          <div className="inline-flex items-center gap-3 mb-6">
            <Sparkles className="w-12 h-12 text-yellow-300 animate-pulse" />
            <h1 className="text-6xl font-black text-transparent bg-clip-text bg-gradient-to-r from-yellow-200 via-pink-200 to-purple-200" dir="rtl">
              מערכת בדיקת תוכניות ממ״ד
            </h1>
            <Zap className="w-12 h-12 text-yellow-300 animate-pulse" />
          </div>
          <p className="text-2xl font-semibold text-purple-100 mb-3" dir="rtl">
            🤖 בדיקה אוטומטית מבוססת בינה מלאכותית
          </p>
          <p className="text-lg text-purple-200 mb-6" dir="rtl">
            מופעל על ידי Azure OpenAI GPT-5.1 עם יכולות חשיבה מתקדמות
          </p>
          
          {/* Demo Plans Section */}
          <div className="bg-white/10 backdrop-blur-lg rounded-3xl p-8 mb-8 border-2 border-white/20 shadow-2xl">
            <h2 className="text-3xl font-bold text-white mb-6 flex items-center justify-center gap-3" dir="rtl">
              <FileText className="w-8 h-8" />
              תוכניות לדוגמה - לחץ לבדיקה מהירה
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {DEMO_PLANS.map((demo) => (
                <button
                  key={demo.name}
                  onClick={() => loadDemoFile(demo.name)}
                  disabled={loading}
                  className={`relative group overflow-hidden rounded-2xl bg-gradient-to-br ${demo.color} p-6 text-white transition-all duration-300 hover:scale-105 hover:shadow-2xl disabled:opacity-50 disabled:cursor-not-allowed ${selectedDemo === demo.name ? 'ring-4 ring-white scale-105' : ''}`}
                >
                  <div className="absolute inset-0 bg-black/20 group-hover:bg-black/10 transition-all"></div>
                  <div className="relative z-10">
                    <div className="text-5xl mb-3">{demo.icon}</div>
                    <h3 className="text-xl font-bold mb-2" dir="rtl">{demo.title}</h3>
                    <p className="text-sm opacity-90" dir="rtl">{demo.description}</p>
                    {selectedDemo === demo.name && (
                      <div className="absolute top-2 right-2">
                        <CheckCircle className="w-6 h-6 text-white" />
                      </div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Upload Section */}
          <div className="bg-white/95 backdrop-blur-xl rounded-3xl shadow-2xl p-10 border-2 border-purple-200">
            <div className="flex items-center gap-4 mb-8">
              <div className="bg-gradient-to-r from-purple-500 to-pink-500 rounded-2xl p-4">
                <Upload className="w-8 h-8 text-white" />
              </div>
              <h2 className="text-3xl font-black text-gray-800" dir="rtl">
                📋 העלאת תוכנית אדריכלית
              </h2>
            </div>

            {/* Project ID Input */}
            <div className="mb-8">
              <label className="block text-xl font-bold text-gray-700 mb-3 flex items-center gap-2" dir="rtl">
                <span className="text-2xl">🏗️</span>
                מזהה פרויקט
              </label>
              <input
                type="text"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="w-full px-6 py-5 text-xl border-3 border-gray-300 rounded-2xl focus:ring-4 focus:ring-purple-400 focus:border-purple-500 transition-all shadow-sm hover:shadow-md"
                placeholder="לדוגמה: demo-project-001"
                dir="rtl"
              />
            </div>

            {/* Drag & Drop Area */}
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              className="relative border-4 border-dashed border-purple-400 bg-gradient-to-br from-purple-50 to-pink-50 rounded-3xl p-16 text-center hover:from-purple-100 hover:to-pink-100 transition-all duration-300 cursor-pointer group overflow-hidden"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-purple-400/0 via-pink-400/20 to-purple-400/0 transform -translate-x-full group-hover:translate-x-full transition-transform duration-1000"></div>
              <input
                type="file"
                id="file-input"
                onChange={handleFileSelect}
                accept="image/*,application/pdf,.dwg"
                className="hidden"
              />
              <label htmlFor="file-input" className="cursor-pointer relative z-10">
                <div className="w-32 h-32 mx-auto mb-6 bg-gradient-to-br from-purple-400 to-pink-500 rounded-full flex items-center justify-center group-hover:scale-110 transition-all shadow-lg group-hover:shadow-2xl">
                  <Upload className="w-16 h-16 text-white animate-bounce" />
                </div>
                <p className="text-2xl font-black text-gray-800 mb-3" dir="rtl">
                  גרור ושחרר את התוכנית כאן
                </p>
                <p className="text-xl font-semibold text-gray-600 mb-3" dir="rtl">
                  או לחץ לבחירת קובץ מהמחשב
                </p>
                <p className="text-base text-gray-500 bg-white/80 inline-block px-6 py-2 rounded-full" dir="rtl">
                  📎 PNG, JPG, PDF עד 10MB
                </p>
              </label>
            </div>

            {/* Preview */}
            {preview && (
              <div className="mt-6 p-4 bg-gray-50 rounded-xl border-2 border-gray-200">
                <p className="text-lg font-semibold text-gray-700 mb-3" dir="rtl">תצוגה מקדימה:</p>
                <img
                  src={preview}
                  alt="תצוגה מקדימה של התוכנית"
                  className="w-full h-72 object-contain border-2 border-gray-300 rounded-xl bg-white shadow-sm"
                />
                <p className="text-base text-gray-600 mt-3 font-medium" dir="rtl">
                  📄 קובץ: {file?.name}
                </p>
              </div>
            )}

            {/* Validate Button */}
            <button
              onClick={handleValidate}
              disabled={!file || loading}
              className="w-full mt-8 bg-gradient-to-r from-green-500 to-emerald-600 text-white py-5 px-8 rounded-xl text-xl font-bold hover:from-green-600 hover:to-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-3 shadow-lg hover:shadow-xl"
              dir="rtl"
            >
              {loading ? (
                <>
                  <Loader2 className="w-6 h-6 animate-spin" />
                  <span>מבצע בדיקה...</span>
                </>
              ) : (
                <>
                  <CheckCircle className="w-6 h-6" />
                  <span>בדוק תוכנית</span>
                </>
              )}
            </button>

            {/* Error Message */}
            {error && (
              <div className="mt-6 p-5 bg-red-50 border-2 border-red-300 rounded-xl" dir="rtl">
                <div className="flex items-start gap-3">
                  <XCircle className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-lg font-bold text-red-800 mb-1">שגיאה</p>
                    <p className="text-base text-red-700">{error}</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Results Section */}
          <div className="bg-white rounded-lg shadow-xl p-8">
            <h2 className="text-3xl font-bold mb-6 text-gray-800" dir="rtl">
              📊 תוצאות הבדיקה
            </h2>

            {!result && !loading && (
              <div className="text-center py-16 text-gray-400">
                <AlertTriangle className="w-20 h-20 mx-auto mb-6 text-gray-300" />
                <p className="text-xl font-medium" dir="rtl">העלה תוכנית לבדיקה</p>
                <p className="text-base mt-2" dir="rtl">התוצאות יופיעו כאן</p>
              </div>
            )}

            {loading && (
              <div className="text-center py-16">
                <Loader2 className="w-20 h-20 mx-auto mb-6 text-purple-600 animate-spin" />
                <p className="text-2xl font-bold text-gray-700 mb-3" dir="rtl">מנתח תוכנית עם GPT-5.1...</p>
                <p className="text-lg text-gray-500 mb-2" dir="rtl">המודל משתמש ביכולות חשיבה מתקדמות</p>
                <p className="text-base text-gray-400" dir="rtl">⏱️ תהליך זה עשוי לקחת 30-90 שניות</p>
              </div>
            )}

            {result && (
              <div className="space-y-8">
                {/* Display Individual Checks as Separate Cards */}
                {result.checks && result.checks.length > 0 && (
                  <div className="space-y-6">
                    <h3 className="font-bold text-3xl text-gray-800" dir="rtl">
                      📋 בדיקות בודדות ({result.checks.length})
                    </h3>
                    {result.checks.map((check, idx) => (
                      <div 
                        key={check.check_id}
                        className={`border-3 rounded-2xl p-6 ${
                          check.status === 'pass' ? 'bg-green-50 border-green-300' :
                          check.status === 'fail' ? 'bg-red-50 border-red-300' :
                          'bg-gray-50 border-gray-300'
                        }`}
                      >
                        {/* Debug: Log bounding box data */}
                        {console.log(`Check ${idx}: ${check.check_name}`, 'BBox:', check.bounding_box)}
                        
                        {/* Check Header */}
                        <div className="flex items-center justify-between mb-4" dir="rtl">
                          <div>
                            <h4 className="font-bold text-2xl mb-2">
                              {check.status === 'pass' ? '✅' : check.status === 'fail' ? '❌' : '⏭️'} {check.check_name}
                            </h4>
                            <p className="text-lg text-gray-700">{check.description}</p>
                          </div>
                          <div className="text-5xl">
                            {check.status === 'pass' ? '🟢' : check.status === 'fail' ? '🔴' : '⚪'}
                          </div>
                        </div>

                        {/* Plan Image with Bounding Box for this specific check */}
                        {check.plan_image_url && (
                          <div className="relative w-full mb-4" style={{ display: 'inline-block', position: 'relative' }}>
                            <img 
                              src={check.plan_image_url} 
                              alt={check.check_name}
                              className="w-full h-auto border-2 border-gray-300 rounded block"
                              style={{ display: 'block', maxWidth: '100%' }}
                            />
                            {check.bounding_box && (
                              <div
                                className="border-[6px] border-red-600 bg-red-600 bg-opacity-30 pointer-events-none"
                                style={{
                                  position: 'absolute',
                                  left: `${check.bounding_box.x}%`,
                                  top: `${check.bounding_box.y}%`,
                                  width: `${check.bounding_box.width}%`,
                                  height: `${check.bounding_box.height}%`,
                                  boxShadow: '0 0 0 2px white, 0 0 20px rgba(220, 38, 38, 0.4)',
                                  zIndex: 10,
                                }}
                              >
                                <div 
                                  className="bg-red-600 text-white px-3 py-1 rounded-md text-sm font-bold whitespace-nowrap shadow-lg border-2 border-white"
                                  style={{
                                    position: 'absolute',
                                    top: '-32px',
                                    left: '-2px',
                                    zIndex: 20,
                                  }}
                                >
                                  {idx + 1}. {check.check_name}
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Reasoning */}
                        {check.reasoning && (
                          <div className="bg-white border-2 border-blue-200 rounded-lg p-4 mb-3">
                            <p className="text-base text-gray-700" dir="rtl">
                              💡 <span className="font-semibold">הסבר:</span> {check.reasoning}
                            </p>
                          </div>
                        )}

                        {/* Violation Details (if failed) */}
                        {check.violation && (
                          <div className="bg-white border-2 border-red-200 rounded-lg p-4">
                            <div className="mb-3">
                              <span className="px-4 py-1 bg-red-500 text-white rounded-full text-sm font-bold">
                                {check.violation.severity === 'critical' ? 'קריטי' : 
                                 check.violation.severity === 'major' ? 'חמור' : 'קל'}
                              </span>
                            </div>
                            <p className="font-bold text-lg mb-2 text-gray-800" dir="rtl">
                              {check.violation.description}
                            </p>
                            {check.violation.location_description && (
                              <p className="text-sm text-gray-600 mb-2" dir="rtl">
                                📍 {check.violation.location_description}
                              </p>
                            )}
                            <div className="grid grid-cols-2 gap-4 mt-3">
                              {check.violation.actual_value && (
                                <div className="bg-red-50 p-3 rounded">
                                  <span className="text-sm text-gray-600 block mb-1" dir="rtl">ערך בפועל:</span>
                                  <span className="font-bold text-red-700" dir="rtl">{check.violation.actual_value}</span>
                                </div>
                              )}
                              {check.violation.expected_value && (
                                <div className="bg-green-50 p-3 rounded">
                                  <span className="text-sm text-gray-600 block mb-1" dir="rtl">ערך נדרש:</span>
                                  <span className="font-bold text-green-700" dir="rtl">{check.violation.expected_value}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Fallback: Old display if checks not available */}
                {(!result.checks || result.checks.length === 0) && result.plan_blob_url && result.violations && result.violations.length > 0 && (
                  <div className="border-3 border-purple-200 rounded-2xl p-6 bg-white">
                    <h3 className="font-bold text-3xl mb-4 text-purple-800" dir="rtl">
                      🖼️ תוכנית עם סימון בעיות
                    </h3>
                    <div className="relative inline-block max-w-full overflow-visible" style={{paddingTop: '40px'}}>
                      <img 
                        src={result.plan_blob_url} 
                        alt="Architectural Plan"
                        className="max-w-full h-auto border-2 border-gray-300 rounded block"
                      />
                      {result.violations.map((violation, idx) => {
                        // Use bounding box if available, otherwise show marker only
                        const bbox = violation.bounding_box || null;
                        
                        return (
                          <div
                            key={idx}
                            className="absolute border-[6px] border-red-600 bg-red-600 bg-opacity-30 cursor-pointer hover:bg-opacity-40 transition pointer-events-auto"
                            style={{
                              left: bbox ? `${bbox.x}%` : '5%',
                              top: bbox ? `${bbox.y}%` : `${10 + idx * 8}%`,
                              width: bbox ? `${bbox.width}%` : '90%',
                              height: bbox ? `${bbox.height}%` : '5%',
                              boxShadow: '0 0 0 2px white, 0 0 20px rgba(220, 38, 38, 0.4)',
                            }}
                            title={`${violation.description}\n\nמיקום: ${violation.location_description || 'לא צוין מיקום מדויק'}`}
                          >
                            <div className="absolute -top-7 -left-1 bg-red-600 text-white px-3 py-1 rounded-md text-xs font-bold whitespace-nowrap shadow-lg z-10 border-2 border-white">
                              {idx + 1}. {violation.severity === 'critical' ? '🔴' : violation.severity === 'major' ? '🟠' : '🟡'}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <p className="text-sm text-gray-600 mt-4" dir="rtl">
                      💡 ריחף מעל התיבות האדומות לראות פרטים נוספים
                    </p>
                  </div>
                )}

                {/* Overall Status - סטטוס כללי */}
                <div className={`p-8 rounded-2xl border-3 shadow-lg ${getOverallStatusColor(result.status)}`}>
                  <div className="flex items-center justify-between" dir="rtl">
                    <div>
                      <h3 className="font-bold text-3xl mb-3">
                        {result.status === 'pass' ? '✅ התוכנית תקינה' : 
                         result.status === 'fail' ? '❌ התוכנית לא תקינה' : 
                         '⚠️ נדרשת בדיקה נוספת'}
                      </h3>
                      <p className="text-2xl font-semibold">
                        {result.passed_checks}/{result.total_checks} בדיקות עברו בהצלחה
                      </p>
                      <p className="text-sm text-gray-600 mt-3">מזהה בדיקה: {result.validation_id}</p>
                    </div>
                    <div className="text-8xl">
                      {result.status === 'pass' ? '🎉' : result.status === 'fail' ? '🔴' : '🔍'}
                    </div>
                  </div>
                </div>

                {/* Extracted Data - מה המודל הבין */}
                <div className="border-3 border-purple-200 rounded-2xl p-8 bg-purple-50">
                  <h3 className="font-bold text-3xl mb-6 text-purple-800" dir="rtl">
                    🧠 מה המודל GPT-5.1 זיהה בתוכנית
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-lg">
                    <div className="bg-white p-6 rounded-xl shadow" dir="rtl">
                      <span className="text-gray-700 font-semibold block mb-2">🧱 מספר קירות חיצוניים:</span>
                      <span className="font-bold text-2xl text-purple-600">
                        {result.extracted_data?.external_wall_count ?? 'לא זוהה'}
                      </span>
                    </div>
                    <div className="bg-white p-6 rounded-xl shadow" dir="rtl">
                      <span className="text-gray-700 font-semibold block mb-2">📏 עובי קירות (ס״מ):</span>
                      <span className="font-bold text-2xl text-purple-600">
                        {result.extracted_data?.wall_thickness_cm && result.extracted_data.wall_thickness_cm.length > 0 
                          ? result.extracted_data.wall_thickness_cm.join(', ') 
                          : 'לא זוהה'}
                      </span>
                    </div>
                    <div className="bg-white p-6 rounded-xl shadow" dir="rtl">
                      <span className="text-gray-700 font-semibold block mb-2">📐 גובה חדר (מ׳):</span>
                      <span className="font-bold text-2xl text-purple-600">
                        {result.extracted_data?.room_height_m ?? 'לא זוהה'}
                      </span>
                    </div>
                    <div className="bg-white p-6 rounded-xl shadow" dir="rtl">
                      <span className="text-gray-700 font-semibold block mb-2">📦 נפח חדר (מ״ק):</span>
                      <span className="font-bold text-2xl text-purple-600">
                        {result.extracted_data?.room_volume_m3 ?? 'לא זוהה'}
                      </span>
                    </div>
                    <div className="bg-white p-6 rounded-xl shadow" dir="rtl">
                      <span className="text-gray-700 font-semibold block mb-2">🚪 מרחק דלת (ס״מ):</span>
                      <span className="font-bold text-2xl text-purple-600">
                        {result.extracted_data?.door_spacing_cm ?? 'לא זוהה'}
                      </span>
                    </div>
                    <div className="bg-white p-6 rounded-xl shadow" dir="rtl">
                      <span className="text-gray-700 font-semibold block mb-2">🪟 מרחק חלון (ס״מ):</span>
                      <span className="font-bold text-2xl text-purple-600">
                        {result.extracted_data?.window_spacing_cm ?? 'לא זוהה'}
                      </span>
                    </div>
                    <div className="bg-white p-6 rounded-xl shadow col-span-1 md:col-span-2" dir="rtl">
                      <span className="text-gray-700 font-semibold block mb-2">💨 הערות אוורור:</span>
                      <span className="font-medium text-lg text-gray-800">
                        {result.extracted_data?.ventilation_notes || 'לא נמצאו הערות'}
                      </span>
                    </div>
                    <div className="bg-gradient-to-r from-green-100 to-emerald-100 p-6 rounded-xl shadow col-span-1 md:col-span-2" dir="rtl">
                      <span className="text-gray-700 font-semibold block mb-2">🎯 רמת ביטחון של המודל:</span>
                      <div className="flex items-center gap-4">
                        <span className="font-bold text-3xl text-green-600">
                          {result.extracted_data?.confidence_score !== undefined 
                            ? `${(result.extracted_data.confidence_score * 100).toFixed(1)}%` 
                            : 'N/A'}
                        </span>
                        <span className="text-sm text-gray-600">
                          (רמת ביטחון נמוכה עלולה להתקבל כאשר התוכנית לא מכילה מספיק פרטים)
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* All Validation Checks - כל הבדיקות */}
                <div className="border-3 border-blue-200 rounded-2xl p-8 bg-blue-50">
                  <h3 className="font-bold text-3xl mb-6 text-blue-800" dir="rtl">
                    📋 פירוט 20 בדיקות הממ״ד
                  </h3>
                  
                  {result?.violations?.length === 0 ? (
                    <div className="text-center py-16 bg-gradient-to-r from-green-100 to-emerald-100 rounded-xl">
                      <CheckCircle className="w-24 h-24 mx-auto mb-6 text-green-600" />
                      <p className="font-bold text-4xl text-green-700 mb-3">כל הבדיקות עברו בהצלחה! 🎉</p>
                      <p className="text-xl text-gray-700">התוכנית עומדת בכל הדרישות של פיקוד העורף</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="bg-red-100 border-2 border-red-300 rounded-xl p-6 mb-6">
                        <h4 className="font-bold text-2xl text-red-700 mb-3" dir="rtl">
                          ⚠️ בעיות שנמצאו ({result?.violations?.length ?? 0})
                        </h4>
                        <div className="space-y-4">
                          {result?.violations?.map((violation, idx) => (
                            <div
                              key={idx}
                              className="bg-white p-6 rounded-xl border-2 border-red-200 shadow-md"
                            >
                              <div className="flex items-start gap-4" dir="rtl">
                                <XCircle className="w-8 h-8 text-red-600 flex-shrink-0 mt-1" />
                                <div className="flex-1">
                                  <div className="flex items-center gap-3 mb-3">
                                    <span className="px-4 py-1 bg-red-500 text-white rounded-full text-sm font-bold">
                                      {violation.severity === 'critical' ? 'קריטי' : 
                                       violation.severity === 'major' ? 'חמור' : 'קל'}
                                    </span>
                                    <span className="text-sm text-gray-500">קטגוריה: {violation.category}</span>
                                  </div>
                                  <p className="font-bold text-xl mb-3 text-gray-800">
                                    {violation.description}
                                  </p>
                                  {violation.message && (
                                    <div className="bg-yellow-50 border-2 border-yellow-200 rounded-lg p-4 mb-3">
                                      <p className="text-base text-gray-700">
                                        💬 <span className="font-semibold">פירוט:</span> {violation.message}
                                      </p>
                                    </div>
                                  )}
                                  {violation.location_description && (
                                    <div className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4 mb-3">
                                      <p className="text-base text-gray-700">
                                        📍 <span className="font-semibold">מיקום בתוכנית:</span> {violation.location_description}
                                      </p>
                                      {violation.bounding_box ? (
                                        <p className="text-sm text-green-600 mt-2 font-semibold flex items-center gap-2">
                                          <span className="inline-block w-4 h-4 bg-red-600 border-2 border-white rounded-sm"></span>
                                          מסומן בריבוע אדום בתמונה למעלה
                                        </p>
                                      ) : (
                                        <p className="text-sm text-orange-600 mt-2 font-semibold">
                                          ⚠️ מיקום מדויק לא זוהה - סימון כללי בתמונה
                                        </p>
                                      )}
                                    </div>
                                  )}
                                  <div className="grid grid-cols-2 gap-4 mt-4">
                                    {violation.actual_value !== undefined && (
                                      <div className="bg-red-50 p-4 rounded-lg">
                                        <span className="text-sm text-gray-600 block mb-1">ערך בפועל:</span>
                                        <span className="font-bold text-lg text-red-700">
                                          {JSON.stringify(violation.actual_value)}
                                        </span>
                                      </div>
                                    )}
                                    {violation.expected_value !== undefined && (
                                      <div className="bg-green-50 p-4 rounded-lg">
                                        <span className="text-sm text-gray-600 block mb-1">ערך נדרש:</span>
                                        <span className="font-bold text-lg text-green-700">
                                          {JSON.stringify(violation.expected_value)}
                                        </span>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                      
                      <div className="bg-green-100 border-2 border-green-300 rounded-xl p-6">
                        <h4 className="font-bold text-2xl text-green-700 mb-3" dir="rtl">
                          ✅ בדיקות שעברו בהצלחה ({result.passed_checks})
                        </h4>
                        <p className="text-lg text-gray-700" dir="rtl">
                          {result.passed_checks} בדיקות נוספות עברו בהצלחה ועומדות בדרישות פיקוד העורף
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Plan Details */}
                {result.plan_blob_url && (
                  <div className="bg-gray-50 border-2 border-gray-200 rounded-xl p-6 text-base text-gray-600" dir="rtl">
                    <p className="mb-2">📄 <span className="font-semibold">שם הקובץ:</span> {result.plan_name}</p>
                    <p>🔗 <span className="font-semibold">קישור:</span> <a href={result.plan_blob_url} target="_blank" rel="noopener noreferrer" className="text-purple-600 hover:underline break-all">{result.plan_blob_url}</a></p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
