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
      <div className="space-y-8">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center shadow-sm border border-primary/20">
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-text-primary">מעבד את התוכנית</h2>
            <p className="text-sm text-text-muted mt-1">ממיר, מזהה ומכין את הסגמנטים לבדיקה</p>
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <div className="flex justify-between text-sm text-text-muted mb-2 font-medium">
              <span>{currentStep}</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
              <div
                className="bg-primary h-full rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          <div className="grid gap-3 text-sm">
            <div className={`rounded-lg px-4 py-3 border transition-colors duration-300 ${progress >= 20 ? 'border-success/20 bg-success/5 text-success font-medium' : 'border-border bg-card text-text-muted'}`}>
              ✅ המרת DWF → PNG (ODA File Converter)
            </div>
            <div className={`rounded-lg px-4 py-3 border transition-colors duration-300 ${progress >= 40 ? 'border-success/20 bg-success/5 text-success font-medium' : 'border-border bg-card text-text-muted'}`}>
              🔍 ניתוח חכם של התוכנית (GPT-5.1)
              {progress >= 40 && progress < 90 && (
                <div className="mt-1 text-xs text-text-muted font-normal">
                  מזהה תוכנית קומה, חתכים ופרטי בניה...
                </div>
              )}
            </div>
            <div className={`rounded-lg px-4 py-3 border transition-colors duration-300 ${progress >= 70 ? 'border-success/20 bg-success/5 text-success font-medium' : 'border-border bg-card text-text-muted'}`}>
              ✂️ חיתוך ושמירת סגמנטים
            </div>
            <div className={`rounded-lg px-4 py-3 border transition-colors duration-300 ${progress >= 90 ? 'border-success/20 bg-success/5 text-success font-medium' : 'border-border bg-card text-text-muted'}`}>
              💾 שמירה למאגר
            </div>
          </div>

          <div className="text-center text-sm text-text-muted">
            ⏱️ תהליך זה מתבצע פעם אחת לכל תוכנית
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-text-primary">העלאת תוכנית אדריכלית</h2>
          <p className="text-sm text-text-muted mt-1">בחר קובץ, או גרור לכאן כדי להתחיל ניתוח חכם</p>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-error/5 border border-error/20 rounded-xl flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-error flex-shrink-0 mt-0.5" />
          <div className="text-sm text-error font-medium">{error}</div>
        </div>
      )}

      <div
        className={`
          border-2 border-dashed rounded-2xl p-10 text-center transition-all duration-300 ease-out
          ${isDragging 
            ? 'border-primary bg-primary/5 scale-[1.01] shadow-lg' 
            : 'border-border bg-card hover:border-primary/50 hover:bg-gray-50/50 hover:shadow-md'
          }
          cursor-pointer
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

        <div className="flex flex-col items-center gap-4">
          <div className={`
            w-16 h-16 rounded-full flex items-center justify-center border transition-colors duration-300
            ${isDragging ? 'bg-primary/10 text-primary border-primary/20' : 'bg-gray-50 text-text-muted border-border'}
          `}>
            <Upload className="w-8 h-8" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-text-primary">גרור קובץ לכאן או לחץ לבחירה</h3>
            <p className="text-sm text-text-muted mt-1">פורמטים: DWF, DWFX, PDF, PNG, JPG · עד 50MB</p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-text-muted mt-2">
            <span className="px-2.5 py-1 rounded-full bg-background border border-border">המרה אוטומטית ל-PNG</span>
            <span className="px-2.5 py-1 rounded-full bg-background border border-border">זיהוי סגמנטים חכם</span>
            <span className="px-2.5 py-1 rounded-full bg-background border border-border">שומר ענן מאובטח</span>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl bg-primary/5 border border-primary/10 p-4">
          <div className="flex items-start gap-3">
            <FileImage className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
            <div className="text-sm text-text-primary leading-relaxed">
              <strong className="font-semibold">המרת DWF אוטומטית</strong> דרך ODA File Converter ללא סימני מים. אם ההמרה נכשלת, ניתן להמיר ידנית ולהעלות PNG.
            </div>
          </div>
        </div>
        <div className="rounded-xl bg-success/5 border border-success/10 p-4">
          <div className="flex items-start gap-3">
            <FileImage className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
            <div className="text-sm text-text-primary leading-relaxed">
              <strong className="font-semibold">איך זה עובד</strong>: GPT-5.1 מזהה תוכנית קומה, חתכים ופרטי בניה ומכין רשימת סגמנטים שתוכל לאשר לבדיקה.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DecompositionUpload;
