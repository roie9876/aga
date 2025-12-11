import { useState, useEffect } from 'react';
import { X, ChevronDown, ChevronUp, BookOpen, CheckCircle2 } from 'lucide-react';
import { Card } from './ui';

interface Subsection {
  title: string;
  requirements: string[];
}

interface Section {
  title: string;
  subsections: Subsection[];
}

interface RequirementsData {
  title: string;
  description: string;
  sections: Section[];
}

interface RequirementsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function RequirementsModal({ isOpen, onClose }: RequirementsModalProps) {
  const [requirements, setRequirements] = useState<RequirementsData | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set([0]));
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (isOpen && !requirements) {
      loadRequirements();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const loadRequirements = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/v1/requirements');
      if (!response.ok) throw new Error('Failed to load requirements');
      const data = await response.json();
      console.log('Requirements loaded:', data);
      setRequirements(data);
    } catch (error) {
      console.error('Error loading requirements:', error);
      alert('שגיאה בטעינת דרישות');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleSection = (index: number) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedSections(newExpanded);
  };

  const expandAll = () => {
    setExpandedSections(new Set(requirements?.sections.map((_, i) => i) || []));
  };

  const collapseAll = () => {
    setExpandedSections(new Set());
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col m-4">
        {/* Header */}
        <div className="bg-gradient-to-r from-primary to-primary/80 text-white px-8 py-6 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-white/20 rounded-lg flex items-center justify-center">
              <BookOpen className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-2xl font-bold">
                {requirements?.title || 'דרישות ממ״ד'}
              </h2>
              <p className="text-white/90 text-sm mt-1">
                {requirements?.description || 'טוען...'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-10 h-10 rounded-lg bg-white/20 hover:bg-white/30 transition-colors flex items-center justify-center"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Controls */}
        {requirements && requirements.sections && (
          <div className="px-8 py-4 border-b border-gray-200 flex items-center justify-between bg-gray-50">
            <div className="text-sm text-gray-600">
              <span className="font-semibold text-gray-900">
                {requirements.sections.reduce((acc, s) => 
                  acc + s.subsections.reduce((total, sub) => total + sub.requirements.length, 0), 0
                )}
              </span>
              {' '}דרישות ב-
              <span className="font-semibold text-gray-900">
                {requirements.sections.length}
              </span>
              {' '}סעיפים
            </div>
            <div className="flex gap-2">
              <button
                onClick={expandAll}
                className="text-sm text-primary hover:text-primary/80 font-medium px-3 py-1 rounded-lg hover:bg-primary/5 transition-colors"
              >
                פתח הכל
              </button>
              <button
                onClick={collapseAll}
                className="text-sm text-gray-600 hover:text-gray-900 font-medium px-3 py-1 rounded-lg hover:bg-gray-100 transition-colors"
              >
                סגור הכל
              </button>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-8 py-6">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin mx-auto mb-4"></div>
                <p className="text-gray-600">טוען דרישות...</p>
              </div>
            </div>
          )}

          {!isLoading && requirements && requirements.sections && (
            <div className="space-y-4">
              {requirements.sections.map((section, sectionIndex) => {
                const isExpanded = expandedSections.has(sectionIndex);
                const requirementsCount = section.subsections.reduce(
                  (acc, sub) => acc + sub.requirements.length, 0
                );

                return (
                  <Card key={sectionIndex} padding="none" className="overflow-hidden">
                    {/* Section Header */}
                    <button
                      onClick={() => toggleSection(sectionIndex)}
                      className="w-full px-6 py-4 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors border-b border-gray-200"
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center flex-shrink-0">
                          <span className="text-primary font-bold text-sm">
                            {sectionIndex + 1}
                          </span>
                        </div>
                        <div className="text-right">
                          <h3 className="font-bold text-gray-900 text-lg">
                            {section.title}
                          </h3>
                          <p className="text-xs text-gray-600 mt-0.5">
                            {requirementsCount} דרישות • {section.subsections.length} סעיפי משנה
                          </p>
                        </div>
                      </div>
                      {isExpanded ? (
                        <ChevronUp className="w-5 h-5 text-gray-400 flex-shrink-0" />
                      ) : (
                        <ChevronDown className="w-5 h-5 text-gray-400 flex-shrink-0" />
                      )}
                    </button>

                    {/* Section Content */}
                    {isExpanded && (
                      <div className="px-6 py-4 space-y-6">
                        {section.subsections.map((subsection, subIndex) => (
                          <div key={subIndex}>
                            {/* Subsection Title */}
                            <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                              <div className="w-6 h-6 bg-primary/5 rounded flex items-center justify-center flex-shrink-0">
                                <span className="text-primary text-xs font-bold">
                                  {sectionIndex + 1}.{subIndex + 1}
                                </span>
                              </div>
                              {subsection.title}
                            </h4>

                            {/* Requirements List */}
                            {subsection.requirements.length > 0 && (
                              <div className="space-y-2 mr-8">
                                {subsection.requirements.map((requirement, reqIndex) => (
                                  <div
                                    key={reqIndex}
                                    className="flex items-start gap-3 text-sm text-gray-700 leading-relaxed bg-white rounded-lg p-3 border border-gray-100 hover:border-primary/20 hover:bg-primary/5 transition-colors"
                                  >
                                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0 mt-0.5" />
                                    <span>{requirement}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-8 py-4 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
          <p className="text-xs text-gray-600">
            המסמך מתייחס <span className="font-semibold">רק לממ״ד</span> ולא לממ״ק/ממ״מ/מקלט
          </p>
          <button
            onClick={onClose}
            className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium"
          >
            סגור
          </button>
        </div>
      </div>
    </div>
  );
}
