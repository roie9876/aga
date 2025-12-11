import React, { useState, useCallback } from 'react';
import { Upload, FileImage, Loader2, AlertCircle } from 'lucide-react';
import type { DecompositionResponse } from '../types';

interface DecompositionUploadProps {
  projectId: string;
  onProjectIdChange?: (projectId: string) => void;
  onDecompositionComplete: (decompositionId: string) => void;
}

export const DecompositionUpload: React.FC<DecompositionUploadProps> = ({
  projectId,
  onProjectIdChange,
  onDecompositionComplete,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileUpload(files[0]);
    }
  }, []);

  const handleFileUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);
    setProgress(0);
    setCurrentStep('מעלה קובץ...');

    try {
      // Step 1: Upload file
      const formData = new FormData();
      formData.append('file', file);
      formData.append('project_id', projectId);

      setProgress(20);
      setCurrentStep('ממיר DWF/DWFX (אם נדרש)...');

      // Simulate progress for user experience
      const progressInterval = setInterval(() => {
        setProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 5;
        });
      }, 2000);

      const response = await fetch('/api/v1/decomposition/analyze', {
        method: 'POST',
        body: formData,
      });

      clearInterval(progressInterval);

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to decompose plan');
      }

      const data: DecompositionResponse = await response.json();
      
      setProgress(100);
      setCurrentStep('הושלם!');
      
      // Wait a bit to show completion
      setTimeout(() => {
        onDecompositionComplete(data.decomposition_id);
      }, 500);

    } catch (err) {
      console.error('Upload error:', err);
      setError(err instanceof Error ? err.message : 'שגיאה בהעלאת הקובץ');
      setIsUploading(false);
    }
  };

  if (isUploading) {
    return (
      <div className="max-w-2xl mx-auto p-8">
        <div className="bg-white rounded-lg shadow-lg p-8">
          <div className="text-center mb-6">
            <Loader2 className="w-16 h-16 mx-auto text-blue-500 animate-spin" />
            <h2 className="text-2xl font-bold mt-4 text-gray-800">
              מעבד את התוכנית
            </h2>
          </div>

          <div className="space-y-6">
            {/* Progress bar */}
            <div>
              <div className="flex justify-between text-sm text-gray-600 mb-2">
                <span>{currentStep}</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-3">
                <div
                  className="bg-blue-500 h-3 rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* Steps */}
            <div className="space-y-3 text-sm">
              <div className={progress >= 20 ? 'text-green-600' : 'text-gray-400'}>
                ✅ המרת DWF → PNG (ODA File Converter)
              </div>
              <div className={progress >= 40 ? 'text-green-600' : 'text-gray-400'}>
                🔍 ניתוח חכם של התוכנית (GPT-5.1)
                {progress >= 40 && progress < 90 && (
                  <div className="mr-6 mt-1 text-xs text-gray-500">
                    מזהה תוכנית קומה, חתכים ופרטים...
                  </div>
                )}
              </div>
              <div className={progress >= 70 ? 'text-green-600' : 'text-gray-400'}>
                ✂️ חיתוך ושמירת סגמנטים
              </div>
              <div className={progress >= 90 ? 'text-green-600' : 'text-gray-400'}>
                💾 שמירה למאגר
              </div>
            </div>

            <div className="text-center text-sm text-gray-500 mt-6">
              ⏱️ תהליך זה מתבצע פעם אחת לכל תוכנית
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="bg-white rounded-lg shadow-lg p-8">
        <h2 className="text-2xl font-bold text-gray-800 mb-6 text-center">
          📤 העלאת תוכנית אדריכלית
        </h2>

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-red-800">{error}</div>
          </div>
        )}

        <div
          className={`
            border-2 border-dashed rounded-lg p-12 text-center transition-all
            ${isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-gray-50'}
            hover:border-blue-400 hover:bg-blue-50 cursor-pointer
          `}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <input
            id="file-input"
            type="file"
            className="hidden"
            accept=".dwf,.dwfx,.pdf,.png,.jpg,.jpeg"
            onChange={handleFileSelect}
          />

          <Upload className="w-16 h-16 mx-auto text-gray-400 mb-4" />
          
          <h3 className="text-lg font-semibold text-gray-700 mb-2">
            גרור קובץ לכאן או לחץ לבחירה
          </h3>
          
          <p className="text-sm text-gray-500 mb-4">
            פורמטים נתמכים: DWF, DWFX, PDF, PNG, JPG
          </p>
          
          <p className="text-xs text-gray-400">
            גודל מקסימלי: 50MB
          </p>
        </div>

        <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-start gap-3">
            <FileImage className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-800">
              <strong>✨ המרת DWF אוטומטית:</strong> המערכת משתמשת ב-ODA File Converter (ללא סימני מים)
              להמרת קבצי DWF/DWFX ל-PNG באופן אוטומטי. אם ההמרה נכשלת, תוכל להמיר ידנית.
            </div>
          </div>
        </div>

        <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
          <div className="flex items-start gap-3">
            <FileImage className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-green-800">
              <strong>💡 איך זה עובד:</strong> GPT-5.1 מנתח את התוכנית, מזהה את תוכנית הקומה הראשית, 
              חתכים ופרטי בניה, ומאפשר לך לבחור אילו סגמנטים רלוונטיים לבדיקת ממ"ד.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DecompositionUpload;
