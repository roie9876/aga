import { useState } from 'react';
import { DecompositionUpload } from './components/DecompositionUpload';
import { DecompositionReview } from './components/DecompositionReview';

type AppStage = 'upload' | 'decomposition_review' | 'validation' | 'results';

function App() {
  const [stage, setStage] = useState<AppStage>('upload');
  const [projectId] = useState('demo-project-001');
  const [decompositionId, setDecompositionId] = useState<string | null>(null);
  const [validationId, setValidationId] = useState<string | null>(null);

  const handleDecompositionComplete = (decompId: string) => {
    setDecompositionId(decompId);
    setStage('decomposition_review');
  };

  const handleApprove = async (approvedSegments: string[]) => {
    if (!decompositionId) return;

    try {
      const response = await fetch(`/api/v1/decomposition/${decompositionId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          approved_segments: approvedSegments,
          rejected_segments: [],
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to approve decomposition');
      }

      const data = await response.json();
      setValidationId(data.validation_id);
      setStage('validation');
      
      // TODO: Start validation process with approved segments
      alert(`✅ אושר! ${approvedSegments.length} סגמנטים נבחרו לבדיקה`);
      
    } catch (err) {
      console.error('Approval error:', err);
      alert('שגיאה באישור הפירוק');
    }
  };

  const handleReject = () => {
    setDecompositionId(null);
    setStage('upload');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                <span className="text-white text-xl font-bold">M</span>
              </div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  מערכת בדיקת תוכניות ממ״ד
                </h1>
                <p className="text-sm text-gray-600">Powered by GPT-5.1 Reasoning</p>
              </div>
            </div>

            {/* Progress indicator */}
            <div className="flex items-center gap-2">
              <div className={`px-3 py-1 rounded text-sm ${
                stage === 'upload' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-600'
              }`}>
                1. העלאה
              </div>
              <div className="text-gray-400">→</div>
              <div className={`px-3 py-1 rounded text-sm ${
                stage === 'decomposition_review' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-600'
              }`}>
                2. סקירה
              </div>
              <div className="text-gray-400">→</div>
              <div className={`px-3 py-1 rounded text-sm ${
                stage === 'validation' || stage === 'results' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-600'
              }`}>
                3. בדיקות
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="py-8">
        {stage === 'upload' && (
          <DecompositionUpload
            projectId={projectId}
            onDecompositionComplete={handleDecompositionComplete}
          />
        )}

        {stage === 'decomposition_review' && decompositionId && (
          <DecompositionReview
            decompositionId={decompositionId}
            onApprove={handleApprove}
            onReject={handleReject}
          />
        )}

        {stage === 'validation' && (
          <div className="max-w-2xl mx-auto p-8 text-center">
            <div className="bg-white rounded-lg shadow-lg p-12">
              <div className="animate-spin w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-6"></div>
              <h2 className="text-2xl font-bold text-gray-800 mb-2">
                מריץ בדיקות על הסגמנטים...
              </h2>
              <p className="text-gray-600">
                GPT-5.1 בודק את כל הדרישות על הסגמנטים שאושרו
              </p>
              <p className="text-sm text-gray-500 mt-4">
                (תכונה זו תשולב בקרוב)
              </p>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 py-3">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex items-center justify-between text-sm text-gray-600">
            <div>
              פרויקט: <strong>{projectId}</strong>
            </div>
            {decompositionId && (
              <div>
                Decomposition ID: <code className="text-xs bg-gray-100 px-2 py-1 rounded">{decompositionId}</code>
              </div>
            )}
            <div>
              © 2025 Mamad Validation System
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
