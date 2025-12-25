import React, { useState } from 'react';
import { CheckCircle2, AlertCircle, ChevronDown } from 'lucide-react';
import { Badge } from './ui';

interface Violation {
  description: string;
  actual_value?: any;
  expected_value?: any;
  segment?: string;
}

interface Requirement {
  requirement_id: string;
  description: string;
  status: 'passed' | 'failed' | 'not_checked';
  severity: 'critical' | 'error' | 'warning' | 'info';
  segments_checked: string[];
  violations: Violation[];
  evaluations?: Array<{
    segment_id?: string;
    status?: string;
    notes_he?: string;
    reason_not_checked?: string;
    evidence?: any[];
  }>;
}

export const RequirementItem: React.FC<{ req: Requirement }> = ({ req }) => {
  const [expanded, setExpanded] = useState(false);
  const hasViolations = req.status === 'failed' && req.violations?.length > 0;
  const hasEvaluations = Array.isArray(req.evaluations) && req.evaluations.length > 0;
  const hasDetails = hasViolations || req.segments_checked?.length > 0 || hasEvaluations;

  const formatEvidence = (evidence: any[]) => {
    if (!Array.isArray(evidence)) return [];
    const lines: string[] = [];
    for (const ev of evidence) {
      if (!ev || typeof ev !== 'object') continue;
      if (ev.evidence_type === 'dimension') {
        const element = String(ev.element || '').toLowerCase();
        const value = ev.value;
        const unit = ev.unit ? ` ${ev.unit}` : '';
        if (element.includes('computed_area')) {
          if (typeof value === 'number') {
            lines.push(`שטח מחושב: ${value.toFixed(2)}${unit}`);
          }
          continue;
        }
        if (element.includes('required_min_area')) {
          lines.push(`מינימום נדרש: ${value}${unit}`);
          continue;
        }
        if (element.includes('mamad_room_length')) {
          lines.push(`אורך פנימי: ${value}${unit}`);
          continue;
        }
        if (element.includes('mamad_room_width')) {
          lines.push(`רוחב פנימי: ${value}${unit}`);
          continue;
        }
        if (value !== undefined) {
          lines.push(`${ev.element || 'מידה'}: ${value}${unit}`);
        }
      } else if (ev.evidence_type === 'text' && typeof ev.text === 'string') {
        lines.push(ev.text.trim());
      }
    }
    return lines;
  };

  const collectSummaryLines = () => {
    const lines: string[] = [];
    if (!Array.isArray(req.evaluations)) return lines;
    for (const ev of req.evaluations) {
      if (ev?.notes_he && typeof ev.notes_he === 'string') {
        lines.push(ev.notes_he.trim());
      }
      const evidenceLines = formatEvidence(ev?.evidence || []);
      for (const line of evidenceLines) {
        lines.push(line);
      }
    }
    return Array.from(new Set(lines)).slice(0, 4);
  };

  const summaryLines = collectSummaryLines();

  return (
    <div 
      className={`transition-all ${
        req.status === 'passed' ? 'bg-success/5 hover:bg-success/10' :
        req.status === 'failed' ? 'bg-error/5 hover:bg-error/10' :
        'bg-white hover:bg-gray-50'
      }`}
    >
      <button
        onClick={() => hasDetails && setExpanded(!expanded)}
        className={`w-full px-5 py-4 text-right ${hasDetails ? 'cursor-pointer' : 'cursor-default'}`}
      >
        <div className="flex items-start gap-4">
          {/* Status Icon */}
          <div className="flex-shrink-0 pt-0.5">
            {req.status === 'passed' && (
              <div className="w-6 h-6 bg-success/20 rounded-full flex items-center justify-center">
                <CheckCircle2 className="w-4 h-4 text-success" />
              </div>
            )}
            {req.status === 'failed' && (
              <div className="w-6 h-6 bg-error/20 rounded-full flex items-center justify-center">
                <AlertCircle className="w-4 h-4 text-error" />
              </div>
            )}
            {req.status === 'not_checked' && (
              <div className="w-6 h-6 bg-gray-100 rounded-full border-2 border-gray-300" />
            )}
          </div>
          
          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-sm font-bold text-text-primary">
                  {req.requirement_id}
                </span>
                <Badge 
                  variant={
                    req.severity === 'critical' ? 'error' :
                    req.severity === 'error' ? 'warning' : 'info'
                  }
                  size="sm"
                >
                  {req.severity}
                </Badge>
                {req.status === 'passed' && (
                  <Badge variant="success" size="sm">✓ עבר</Badge>
                )}
                {req.status === 'failed' && (
                  <Badge variant="error" size="sm">✗ נכשל</Badge>
                )}
              </div>
              {hasDetails && (
                <ChevronDown 
                  className={`w-4 h-4 text-text-muted transition-transform flex-shrink-0 ${expanded ? 'rotate-180' : ''}`}
                />
              )}
            </div>
            <p className="text-sm text-text-primary mb-1 leading-relaxed text-right">{req.description}</p>
            
            {/* Collapsed info */}
            {!expanded && req.segments_checked?.length > 0 && (
              <p className="text-xs text-text-muted mt-2 text-right">
                נבדק בסגמנטים: {req.segments_checked.slice(0, 3).join(', ')}
                {req.segments_checked.length > 3 && ` +${req.segments_checked.length - 3}`}
              </p>
            )}
            {!expanded && summaryLines.length > 0 && req.status !== 'not_checked' && (
              <p className="text-xs text-text-muted mt-2 text-right">
                סיכום בדיקה: {summaryLines[0]}
              </p>
            )}
          </div>
        </div>
      </button>
      
      {/* Expanded Details */}
      {expanded && hasDetails && (
        <div className="px-5 pb-4 space-y-3 border-t border-border/50">
          {summaryLines.length > 0 && req.status !== 'not_checked' && (
            <div className="mt-3 p-3 bg-white rounded-lg border border-border">
              <p className="text-xs font-semibold text-text-primary mb-2 text-right">
                סיכום הבדיקה:
              </p>
              <div className="space-y-1 text-xs text-text-muted text-right">
                {summaryLines.map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
              </div>
            </div>
          )}
          {/* Segments Checked */}
          {req.segments_checked?.length > 0 && (
            <div className="mt-3 p-3 bg-white rounded-lg border border-border">
              <p className="text-xs font-semibold text-text-primary mb-2 text-right">
                נבדק בסגמנטים ({req.segments_checked.length}):
              </p>
              <div className="flex flex-wrap gap-2 justify-end">
                {req.segments_checked.map((seg: string, i: number) => (
                  <Badge key={i} variant="info" size="sm">{seg}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Evaluation Evidence */}
          {hasEvaluations && (
            <div className="mt-3 p-3 bg-white rounded-lg border border-border">
              <p className="text-xs font-semibold text-text-primary mb-2 text-right">
                פירוט חישוב/ראיות:
              </p>
              <div className="space-y-2 text-xs text-text-muted text-right">
                {req.evaluations?.map((ev, idx) => {
                  const evidenceLines = formatEvidence(ev?.evidence || []);
                  if (!ev && evidenceLines.length === 0) return null;
                  return (
                    <div key={idx} className="border border-border/60 rounded-md p-2 bg-background/60">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-text-primary">
                          {ev?.segment_id ? `סגמנט ${ev.segment_id}` : 'סגמנט'}
                        </span>
                        {ev?.status && <span className="text-text-muted">סטטוס: {ev.status}</span>}
                      </div>
                      {ev?.notes_he && <div className="mt-1 text-text-muted">{ev.notes_he}</div>}
                      {evidenceLines.length > 0 && (
                        <div className="mt-1">
                          {evidenceLines.map((line, i) => (
                            <div key={i}>{line}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          
          {/* Violations */}
          {hasViolations && (
            <div className="mt-3 p-4 bg-error/5 border border-error/20 rounded-lg">
              <div className="flex items-center gap-2 mb-3 justify-end">
                <p className="text-sm font-bold text-error">
                  נמצאו {req.violations.length} הפרות:
                </p>
                <AlertCircle className="w-4 h-4 text-error" />
              </div>
              <div className="space-y-3">
                {req.violations.map((v: Violation, i: number) => (
                  <div key={i} className="bg-white rounded-lg p-3 border border-error/10">
                    <div className="flex items-start gap-2">
                      <div className="flex-1 space-y-2">
                        <div className="flex items-start gap-2">
                          <span className="text-error font-bold text-sm">{i + 1}.</span>
                          <p className="text-sm text-error font-medium text-right flex-1">{v.description}</p>
                        </div>
                        
                        {/* Show actual vs expected values */}
                        {(v.actual_value !== undefined || v.expected_value !== undefined) && (
                          <div className="grid grid-cols-2 gap-3 mt-2">
                            {v.expected_value !== undefined && (
                              <div className="bg-gray-50 rounded p-2 border border-gray-200 text-right">
                                <p className="text-xs text-text-muted font-medium mb-1">נדרש:</p>
                                <p className="text-sm font-bold text-text-primary">{v.expected_value}</p>
                              </div>
                            )}
                            {v.actual_value !== undefined && (
                              <div className="bg-error/5 rounded p-2 border border-error/20 text-right">
                                <p className="text-xs text-error/70 font-medium mb-1">נמצא:</p>
                                <p className="text-sm font-bold text-error">{v.actual_value}</p>
                              </div>
                            )}
                          </div>
                        )}
                        
                        {/* Segment info */}
                        {v.segment && (
                          <p className="text-xs text-text-muted text-right">
                            <span className="font-medium">סגמנט:</span> {v.segment}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
