import { AlertCircle, CheckCircle2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Badge, Button, Card } from './ui';

export type PreflightStatus = 'passed' | 'failed' | 'warning' | 'not_applicable' | 'error';

export interface PreflightCheckResult {
  check_id: string;
  title: string;
  explanation?: string;
  source_pages: number[];
  status: PreflightStatus;
  details: string;
  evidence_segment_ids: string[];
}

export interface SubmissionPreflightResponse {
  passed: boolean;
  summary: string;
  checks: PreflightCheckResult[];
}

export type SegmentAnalysisStatus = 'pending' | 'running' | 'done' | 'error';

export interface SegmentAnalysisProgress {
  total: number;
  done: number;
  statusBySegmentId: Record<string, SegmentAnalysisStatus>;
  errorBySegmentId?: Record<string, string>;
}

const statusToBadgeVariant = (status: PreflightStatus): 'success' | 'error' | 'warning' | 'neutral' => {
  if (status === 'passed') return 'success';
  if (status === 'failed' || status === 'error') return 'error';
  if (status === 'warning') return 'warning';
  return 'neutral';
};

const statusToLabel = (status: PreflightStatus): string => {
  if (status === 'passed') return 'עבר';
  if (status === 'failed') return 'נכשל';
  if (status === 'warning') return 'אזהרה';
  if (status === 'not_applicable') return 'לא רלוונטי';
  return 'שגיאה';
};

export function PreflightChecks(props: {
  loading: boolean;
  result: SubmissionPreflightResponse | null;
  onBack: () => void;
  onContinue: (force?: boolean) => void;
  continueEnabled: boolean;
  analysisProgress?: SegmentAnalysisProgress | null;
  onOpenEvidenceSegment?: (segmentId: string) => void;
}) {
  const { loading, result, onBack, onContinue, continueEnabled, analysisProgress, onOpenEvidenceSegment } = props;
  const [expandedCheckId, setExpandedCheckId] = useState<string | null>(null);
  const [forceContinue, setForceContinue] = useState(false);
  const checks = useMemo(() => (result?.checks || []), [result]);
  const canContinue = continueEnabled || forceContinue;

  const progressList = useMemo(() => {
    const byId = analysisProgress?.statusBySegmentId || {};
    const ids = Object.keys(byId);
    ids.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    return ids.map((id) => ({ id, status: byId[id] }));
  }, [analysisProgress]);

  return (
    <div className="max-w-4xl mx-auto">
      <div className="text-center mb-10">
        <h2 className="text-3xl font-bold text-text-primary mb-3 tracking-tight">בדיקת תנאי סף להגשה</h2>
        <p className="text-text-muted text-lg max-w-2xl mx-auto">
          לפני שמריצים וולידציה, נוודא שהועלו השרטוטים והחתימות הבסיסיים לפי מדריך ההגשה.
        </p>
      </div>

      <Card padding="lg" className="shadow-lg">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
              result?.passed ? 'bg-success/10' : 'bg-warning/10'
            }`}>
              {result?.passed ? (
                <CheckCircle2 className="w-5 h-5 text-success" />
              ) : (
                <AlertCircle className="w-5 h-5 text-warning" />
              )}
            </div>
            <div>
              <div className="text-sm font-semibold text-text-primary">סטטוס תנאי סף</div>
              <div className="text-xs text-text-muted mt-1">
                {loading ? 'מריץ בדיקה…' : (result?.summary || 'טרם הורצה')}
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            <Button variant="ghost" onClick={onBack} disabled={loading}>
              חזור לבחירה
            </Button>
            <Button onClick={() => onContinue(forceContinue)} disabled={loading || !canContinue}>
              המשך לבדיקה
            </Button>
          </div>
        </div>

        {!loading && result && !result.passed && (
          <div className="mt-4 text-sm text-text-muted flex items-center gap-3">
            <label className="inline-flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={forceContinue}
                onChange={(event) => setForceContinue(event.target.checked)}
              />
              <span>אני מבין/ה ורוצה להמשיך למרות כשל בתנאי הסף</span>
            </label>
          </div>
        )}

        {loading && analysisProgress && analysisProgress.total > 0 && (
          <div className="mt-6 rounded-lg border border-border bg-white p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-text-primary">ניתוח סגמנטים בזמן אמת</div>
              <div className="text-xs text-text-muted">
                {Math.min(analysisProgress.done, analysisProgress.total)}/{analysisProgress.total}
              </div>
            </div>

            {progressList.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {progressList.map(({ id, status }) => {
                  const variant = status === 'done' ? 'success' : status === 'error' ? 'error' : status === 'running' ? 'warning' : 'neutral';
                  const label = status === 'done' ? 'הושלם' : status === 'error' ? 'שגיאה' : status === 'running' ? 'רץ' : 'ממתין';
                  const err = analysisProgress?.errorBySegmentId?.[id];
                  return (
                    <button
                      key={id}
                      type="button"
                      className="text-left"
                      onClick={() => onOpenEvidenceSegment?.(id)}
                      title={err ? `${id} – ${label}: ${err}` : `${id} – ${label}`}
                    >
                      <Badge variant={variant as any}>{id} · {label}</Badge>
                    </button>
                  );
                })}
              </div>
            )}

            <div className="text-xs text-text-muted mt-3">
              אפשר ללחוץ על סגמנט כדי לראות את התמונה.
            </div>
          </div>
        )}

        <div className="mt-8 space-y-3">
          {checks.length === 0 ? (
            <div className="text-sm text-text-muted">
              {loading ? 'מחשב תוצאות…' : 'אין תוצאות להצגה.'}
            </div>
          ) : (
            checks.map((c) => {
              const isExpanded = expandedCheckId === c.check_id;
              const hasExplanation = Boolean(c.explanation && String(c.explanation).trim());
              return (
                <div key={c.check_id} className="rounded-lg border border-border bg-white p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          className="text-left text-sm font-bold text-text-primary hover:underline"
                          onClick={() => {
                            if (!hasExplanation) return;
                            setExpandedCheckId((prev) => (prev === c.check_id ? null : c.check_id));
                          }}
                          disabled={!hasExplanation}
                          aria-expanded={isExpanded}
                        >
                          {c.check_id} – {c.title}
                        </button>
                        <Badge variant={statusToBadgeVariant(c.status)}>{statusToLabel(c.status)}</Badge>
                        {hasExplanation && (
                          <button
                            type="button"
                            className="text-xs text-primary hover:underline"
                            onClick={() => setExpandedCheckId((prev) => (prev === c.check_id ? null : c.check_id))}
                          >
                            מה זה?
                          </button>
                        )}
                      </div>

                      <div className="text-xs text-text-muted mt-1">
                        מקור: עמודים {Array.isArray(c.source_pages) && c.source_pages.length ? c.source_pages.join(', ') : '—'}
                      </div>

                      {isExpanded && hasExplanation && (
                        <div className="text-xs text-text-muted mt-2 leading-relaxed">
                          {c.explanation}
                        </div>
                      )}

                      <div className="text-sm text-text-muted mt-2 leading-relaxed">{c.details}</div>
                    </div>

                    {Array.isArray(c.evidence_segment_ids) && c.evidence_segment_ids.length > 0 && (
                      <div className="text-xs text-text-muted whitespace-nowrap">
                        ראיות:{' '}
                        {c.evidence_segment_ids.slice(0, 3).map((sid, idx) => (
                          <span key={sid}>
                            <button
                              type="button"
                              className="text-primary hover:underline"
                              onClick={() => onOpenEvidenceSegment?.(sid)}
                            >
                              {sid}
                            </button>
                            {idx < Math.min(3, c.evidence_segment_ids.length) - 1 ? ', ' : ''}
                          </span>
                        ))}
                        {c.evidence_segment_ids.length > 3 ? '…' : ''}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Card>

      <div className="mt-10 text-center">
        <div className="text-xs text-text-muted">
          פירוט מלא של תנאי הסף נמצא במסמך הרשמי באתר פיקוד העורף:{' '}
          <a
            href="https://www.oref.org.il/media/d0chkjnc/%D7%90%D7%95%D7%A4%D7%9F-%D7%A2%D7%A8%D7%99%D7%9B%D7%AA-%D7%A0%D7%A1%D7%A4%D7%97-%D7%9E%D7%99%D7%92%D7%95%D7%9F-%D7%95%D7%94%D7%92%D7%A9%D7%AA%D7%95.pdf"
            target="_blank"
            rel="noreferrer"
            className="text-primary hover:underline"
          >
            הורדה (PDF)
          </a>
        </div>
      </div>
    </div>
  );
}
