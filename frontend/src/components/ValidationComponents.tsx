import React from 'react';
import { Upload, FileText, CheckCircle2, Loader2 } from 'lucide-react';
import { Card, Badge, Button } from './ui';

interface StepIndicatorProps {
  currentStep: number;
  steps: {
    number: number;
    title: string;
    description: string;
  }[];
}

export const StepIndicator: React.FC<StepIndicatorProps> = ({ currentStep, steps }) => {
  return (
    <div className="w-full max-w-4xl mx-auto mb-12 px-4">
      <div className="relative">
        {/* Progress line */}
        <div className="absolute top-8 left-0 right-0 h-0.5 bg-border -z-10">
          <div 
            className="h-full bg-primary transition-all duration-500 ease-out"
            style={{ width: `${((currentStep - 1) / (steps.length - 1)) * 100}%` }}
          />
        </div>
        
        {/* Steps */}
        <div className="flex justify-between">
          {steps.map((step) => {
            const isCompleted = step.number < currentStep;
            const isCurrent = step.number === currentStep;
            
            return (
              <div key={step.number} className="flex flex-col items-center group">
                <div className={`
                  w-16 h-16 rounded-2xl flex items-center justify-center text-lg font-bold
                  transition-all duration-300 mb-4 border-2 relative
                  ${isCompleted 
                    ? 'bg-primary border-primary text-white shadow-lg shadow-primary/20' 
                    : isCurrent 
                      ? 'bg-card border-primary text-primary shadow-xl shadow-primary/10 ring-4 ring-primary/5 scale-110' 
                      : 'bg-card border-border text-text-muted group-hover:border-primary/30 group-hover:text-text-primary'
                  }
                `}>
                  {isCompleted ? <CheckCircle2 className="w-7 h-7" /> : step.number}
                  
                  {/* Pulse effect for current step */}
                  {isCurrent && (
                    <span className="absolute inset-0 rounded-2xl bg-primary/10 animate-ping" />
                  )}
                </div>
                <div className="text-center">
                  <div className={`text-sm font-bold mb-1 transition-colors duration-200 ${
                    isCurrent ? 'text-primary' : 'text-text-primary'
                  }`}>
                    {step.title}
                  </div>
                  <div className="text-xs text-text-muted font-medium max-w-[120px] mx-auto leading-relaxed">
                    {step.description}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

interface FileUploadZoneProps {
  onFileSelect: (file: File) => void;
  accept?: string;
  maxSize?: number;
  loading?: boolean;
}

export const FileUploadZone: React.FC<FileUploadZoneProps> = ({ 
  onFileSelect, 
  accept = '.pdf,.png,.jpg,.jpeg',
  maxSize = 50 * 1024 * 1024, // 50MB
  loading = false
}) => {
  const [isDragging, setIsDragging] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  
  const handleDragLeave = () => {
    setIsDragging(false);
  };
  
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const file = e.dataTransfer.files[0];
    if (file) {
      if (file.size > maxSize) {
        alert(`הקובץ גדול מדי. גודל מקסימלי: ${maxSize / (1024 * 1024)}MB`);
        return;
      }
      onFileSelect(file);
    }
  };
  
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.size > maxSize) {
        alert(`הקובץ גדול מדי. גודל מקסימלי: ${maxSize / (1024 * 1024)}MB`);
        return;
      }
      onFileSelect(file);
    }
  };
  
  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => !loading && fileInputRef.current?.click()}
      className={`
        relative border-2 border-dashed rounded-2xl p-16 text-center cursor-pointer
        transition-all duration-300 ease-out group
        ${isDragging 
          ? 'border-primary bg-primary/5 scale-[1.01] shadow-lg' 
          : 'border-border hover:border-primary/50 bg-card hover:bg-gray-50/50 shadow-sm hover:shadow-md'
        }
        ${loading ? 'opacity-75 cursor-not-allowed' : ''}
      `}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleFileChange}
        className="hidden"
        disabled={loading}
      />
      
      <div className="flex flex-col items-center gap-6">
        <div className={`
          w-20 h-20 rounded-full flex items-center justify-center
          transition-all duration-300 border
          ${isDragging 
            ? 'bg-primary/10 text-primary border-primary/20 scale-110' 
            : 'bg-background text-text-muted border-border group-hover:bg-primary/5 group-hover:text-primary group-hover:border-primary/20'
          }
        `}>
          {loading ? (
            <Loader2 className="w-10 h-10 animate-spin text-primary" />
          ) : (
            <Upload className="w-10 h-10" />
          )}
        </div>
        
        <div className="space-y-2">
          <p className="text-xl font-bold text-text-primary">
            {loading ? 'מעלה קובץ...' : 'גרור קובץ לכאן או לחץ לבחירה'}
          </p>
          <p className="text-sm text-text-muted">
            PDF, PNG, JPG עד {maxSize / (1024 * 1024)}MB
          </p>
        </div>
        
        {!loading && (
          <Button variant="outline" className="pointer-events-none">
            <FileText className="w-4 h-4 ml-2" />
            בחר קובץ מהמחשב
          </Button>
        )}
      </div>
    </div>
  );
};

interface SegmentCardProps {
  segment: {
    segment_id: string;
    title: string;
    description: string;
    confidence: number;
    thumbnail_url?: string;
    blob_url?: string;
  };
  onApprove?: () => void;
  onReject?: () => void;
  compact?: boolean;
}

export const SegmentCard: React.FC<SegmentCardProps> = ({ 
  segment, 
  onApprove, 
  onReject,
  compact = false 
}) => {
  
  const confidenceVariant = segment.confidence >= 0.8 
    ? 'success'
    : segment.confidence >= 0.6 
    ? 'warning'
    : 'error';
  
  return (
    <Card className="overflow-hidden hover:shadow-lg transition-all duration-300 group">
      <div className={`${compact ? 'p-4' : 'p-6'}`}>
        <div className="flex gap-5">
          {/* Image */}
          <div className="flex-shrink-0">
            <div className="relative overflow-hidden rounded-lg border border-border bg-muted w-32 h-32">
              {segment.thumbnail_url || segment.blob_url ? (
                <img 
                  src={segment.thumbnail_url || segment.blob_url} 
                  alt={segment.title}
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-text-muted">
                  <FileText className="w-8 h-8 opacity-20" />
                </div>
              )}
            </div>
          </div>
          
          {/* Content */}
          <div className="flex-1 min-w-0 flex flex-col justify-between">
            <div>
              <div className="flex items-start justify-between gap-3 mb-2">
                <h3 className="text-lg font-bold text-text-primary truncate pr-1">
                  {segment.title}
                </h3>
                <Badge variant={confidenceVariant as any}>
                  {Math.round(segment.confidence * 100)}%
                </Badge>
              </div>
              <p className="text-sm text-text-muted line-clamp-2 leading-relaxed">
                {segment.description}
              </p>
            </div>
            
            {/* Actions */}
            {(onApprove || onReject) && (
              <div className="flex items-center gap-3 mt-4 pt-2">
                {onApprove && (
                  <Button
                    onClick={onApprove}
                    className="flex-1"
                  >
                    אשר
                  </Button>
                )}
                {onReject && (
                  <Button
                    onClick={onReject}
                    variant="outline"
                    className="flex-1"
                  >
                    דחה
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
};
