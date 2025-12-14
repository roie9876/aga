import { useEffect, useMemo, useRef, useState } from 'react';
import { 
  CheckCircle2, 
  Sparkles, 
  Loader2, 
  History, 
  FileText,
  Download,
  AlertCircle,
  TrendingUp,
  Shield,
  BookOpen,
  Plus
} from 'lucide-react';
import { DecompositionUpload } from './components/DecompositionUpload';
import { DecompositionReview } from './components/DecompositionReview';
import { RequirementItem } from './components/RequirementItem';
import { RequirementsModal } from './components/RequirementsModal';
import { Button, Card, StatCard, Badge, ProgressBar, EmptyState, FloatingActionButton } from './components/ui';
import { StepIndicator } from './components/ValidationComponents';

type WorkflowStage = 'upload' | 'decomposition_review' | 'validation' | 'results' | 'history';

type RequirementStatus = 'passed' | 'failed' | 'not_checked';

const normalizeRequirementId = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  const id = value.trim();
  if (!id) return null;

  // Normalize legacy/internal rule ids used in violations (e.g., "REQ_1_2" -> "1.2").
  const m = /^REQ_(\d+)(?:_(\d+))?$/.exec(id);
  if (m) {
    return m[2] ? `${m[1]}.${m[2]}` : m[1];
  }

  // Keep typical requirement id shapes like 1, 1.2, 3.1 etc; otherwise return as-is.
  return id;
};

const computeOverallRequirementStatus = (validationResult: any): Record<string, RequirementStatus> => {
  const status: Record<string, RequirementStatus> = {};
  const seen: Record<string, { passed: boolean; failed: boolean; notChecked: boolean }> = {};

  const segments: any[] = Array.isArray(validationResult?.segments)
    ? validationResult.segments
    : (Array.isArray(validationResult?.analyzed_segments) ? validationResult.analyzed_segments : []);

  for (const seg of segments) {
    const validation = seg?.validation || {};

    const reqEvals: any[] = Array.isArray(validation?.requirement_evaluations)
      ? validation.requirement_evaluations
      : [];
    for (const ev of reqEvals) {
      const rid = normalizeRequirementId(ev?.requirement_id);
      if (!rid) continue;
      (seen[rid] ||= { passed: false, failed: false, notChecked: false });
      const s = String(ev?.status || '').toLowerCase();
      if (s === 'passed' || s === 'pass') seen[rid].passed = true;
      else if (s === 'failed' || s === 'fail') seen[rid].failed = true;
      else if (s === 'not_checked' || s === 'skip' || s === 'skipped') seen[rid].notChecked = true;
    }

    // If segment is explicitly "passed", treat checked_requirements as evidence of pass.
    const checkedReqs: unknown = validation?.checked_requirements;
    const segStatus = String(validation?.status || '').toLowerCase();
    const segPassed = Boolean(validation?.passed) || segStatus === 'passed' || segStatus === 'pass';
    if (segPassed && Array.isArray(checkedReqs)) {
      for (const r of checkedReqs) {
        const rid = normalizeRequirementId(r);
        if (!rid) continue;
        (seen[rid] ||= { passed: false, failed: false, notChecked: false });
        seen[rid].passed = true;
      }
    }

    // Violations are evidence of failure.
    const violations: any[] = Array.isArray(validation?.violations) ? validation.violations : [];
    for (const v of violations) {
      const rid = normalizeRequirementId(v?.rule_id);
      if (!rid) continue;
      (seen[rid] ||= { passed: false, failed: false, notChecked: false });
      seen[rid].failed = true;
    }
  }

  // Prefer evidence-based aggregation (pass if any segment passed).
  for (const [rid, flags] of Object.entries(seen)) {
    status[rid] = flags.passed ? 'passed' : flags.failed ? 'failed' : 'not_checked';
  }

  // Merge in server coverage ids (for ids that had no per-segment evidence)
  const coverageReqs = validationResult?.coverage?.requirements;
  if (coverageReqs && typeof coverageReqs === 'object') {
    for (const [rid, req] of Object.entries(coverageReqs)) {
      if (status[rid as string]) continue;
      const s = String((req as any)?.status || '').toLowerCase();
      if (s === 'passed') status[rid as string] = 'passed';
      else if (s === 'failed') status[rid as string] = 'failed';
      else if (s === 'not_checked') status[rid as string] = 'not_checked';
    }
  }

  return status;
};

const translateDemoFocusText = (text: string): string => {
  if (!text) return text;
  // Replace enum-like tokens (UPPER_SNAKE_CASE) with Hebrew labels when we have them.
  return text.replace(/\b[A-Z_]{3,}\b/g, (token) => translateModelCategory(token));
};

const toSimpleOneLiner = (text: string): string => {
  const t = String(text || '').trim();
  if (!t) return 'אין תיאור זמין לדרישה זו.';
  const firstLine = t.split('\n').map((s) => s.trim()).find(Boolean) || t;
  const sentence = firstLine.split(/(?<=[.!?])\s+/)[0] || firstLine;
  return sentence.length > 180 ? `${sentence.slice(0, 180).trim()}…` : sentence;
};

// Translate model classification categories (backend emits UPPER_SNAKE_CASE)
const translateModelCategory = (category: string): string => {
  const key = String(category || '').trim().toUpperCase();
  const map: Record<string, string> = {
    WALL_SECTION: 'חתך קיר',
    ROOM_LAYOUT: 'פריסת חדר',
    DOOR_DETAILS: 'פרטי דלת',
    WINDOW_DETAILS: 'פרטי חלון',
    REBAR_DETAILS: 'פרטי זיון',
    MATERIALS_SPECS: 'מפרט חומרים',
    GENERAL_NOTES: 'הערות כלליות',
    SECTIONS: 'חתכים',
    OTHER: 'אחר',
    UNKNOWN: 'לא ידוע',
  };
  return map[key] || (category ? String(category) : 'לא ידוע');
};

// Helper to translate category names (from enum to Hebrew)
const translateCategory = (category: string): string => {
  const categories: Record<string, string> = {
    'floor_plan': 'תוכנית קומה',
    'section': 'חתך',
    'detail': 'פרט',
    'elevation': 'חזית',
    'rebar_details': 'פרטי חיזוק',
    'room_layout': 'פריסת חדר',
    'structural_detail': 'פרט קונסטרוקטיבי',
    'unknown': 'לא ידוע',
  };
  
  return categories[category.toLowerCase()] || category;
};

const translateAnyCategory = (category: string): string => {
  const raw = String(category || '').trim();
  if (!raw) return 'לא ידוע';
  const upper = raw.toUpperCase();
  // If it's enum-like (UPPER_SNAKE_CASE), prefer the model-category translation.
  if (upper === raw && /_/.test(raw)) {
    return translateModelCategory(raw);
  }
  return translateCategory(raw);
};

// Helper to translate segment types (from enum to Hebrew)
const translateType = (type: string): string => {
  const types: Record<string, string> = {
    'floor_plan': 'תוכנית קומה',
    'section': 'חתך',
    'detail': 'פרט',
    'elevation': 'חזית',
    'legend': 'מקרא',
    'table': 'טבלה',
    'unknown': 'לא ידוע',
  };
  
  return types[type?.toLowerCase()] || type || 'לא ידוע';
};

// Calculate real-time coverage statistics from validation data
const calculateCoverageStatistics = (validationResult: any) => {
  // Prefer backend-calculated statistics when available (they are derived from validator checks)
  const backendStats = validationResult?.coverage?.statistics;
  if (backendStats && typeof backendStats.total_requirements === 'number') {
    return backendStats;
  }

  // Fallback: compute from by_category if present
  if (!validationResult?.coverage?.by_category) {
    return {
      total_requirements: 0,
      checked: 0,
      passed: 0,
      failed: 0,
      not_checked: 0,
      coverage_percentage: 0,
      pass_percentage: 0
    };
  }

  const allRequirements: any[] = [];
  Object.values(validationResult.coverage.by_category).forEach((categoryReqs: any) => {
    allRequirements.push(...categoryReqs);
  });

  const total = allRequirements.length;
  const passed = allRequirements.filter((r: any) => r.status === 'passed').length;
  const failed = allRequirements.filter((r: any) => r.status === 'failed').length;
  const notChecked = allRequirements.filter((r: any) => r.status === 'not_checked').length;
  const checked = total - notChecked;
  const coveragePercentage = total > 0 ? (checked / total * 100) : 0;
  const passPercentage = total > 0 ? (passed / total * 100) : 0;

  return {
    total_requirements: total,
    checked,
    passed,
    failed,
    not_checked: notChecked,
    coverage_percentage: Math.round(coveragePercentage * 10) / 10,
    pass_percentage: Math.round(passPercentage * 10) / 10
  };
};

// Calculate coverage statistics using *effective* (global) requirement status where
// pass wins over fail across segments.
const calculateEffectiveCoverageStatistics = (
  validationResult: any,
  overallRequirementStatus: Record<string, RequirementStatus>
) => {
  const coverageReqs = validationResult?.coverage?.requirements;
  const byCat = validationResult?.coverage?.by_category;

  const reqIds: string[] = [];
  if (coverageReqs && typeof coverageReqs === 'object') {
    reqIds.push(...Object.keys(coverageReqs));
  } else if (byCat && typeof byCat === 'object') {
    for (const reqs of Object.values(byCat)) {
      if (!Array.isArray(reqs)) continue;
      for (const r of reqs) {
        if (r?.requirement_id) reqIds.push(String(r.requirement_id));
      }
    }
  }

  // Fallback: use backend stats if we have no ids.
  if (reqIds.length === 0) {
    return calculateCoverageStatistics(validationResult);
  }

  let passed = 0;
  let failed = 0;
  let notChecked = 0;

  for (const rid of reqIds) {
    const fromOverall = overallRequirementStatus[rid];
    const fromCoverage = (coverageReqs && typeof coverageReqs === 'object') ? (coverageReqs as any)[rid]?.status : undefined;
    const s = (fromOverall || fromCoverage || 'not_checked') as RequirementStatus;
    if (s === 'passed') passed += 1;
    else if (s === 'failed') failed += 1;
    else notChecked += 1;
  }

  const total = reqIds.length;
  const checked = total - notChecked;
  const coveragePercentage = total > 0 ? (checked / total * 100) : 0;
  const passPercentage = total > 0 ? (passed / total * 100) : 0;

  return {
    total_requirements: total,
    checked,
    passed,
    failed,
    not_checked: notChecked,
    coverage_percentage: Math.round(coveragePercentage * 10) / 10,
    pass_percentage: Math.round(passPercentage * 10) / 10,
  };
};

function App() {
  const DEMO_MODE = true;
  const [stage, setStage] = useState<WorkflowStage>('upload');
  const [decompositionId, setDecompositionId] = useState<string | null>(null);
  const [projectId] = useState<string>('demo-project-001');
  const [lastApprovedSegmentIds, setLastApprovedSegmentIds] = useState<string[]>([]);
  const [decompositionSnapshot, setDecompositionSnapshot] = useState<any | null>(null);
  const [validationProgress, setValidationProgress] = useState<{
    total: number;
    current: number;
    currentSegment: string;
  } | null>(null);
  const [validationLive, setValidationLive] = useState<{
    segmentId: string | null;
    stage: string;
    logs: Array<{ ts: number; line: string }>;
    door31: { status?: string; reason_not_checked?: string } | null;
    segmentMeta?: { title?: string; type?: string; description?: string } | null;
    analysisSummary?: {
      primary_category?: string;
      description_he?: string;
      explanation_he?: string;
      evidence?: string[];
      relevant_requirements?: string[];
    } | null;
    doorFocusSummary?: {
      internal_clearance_cm?: number | null;
      external_clearance_cm?: number | null;
      confidence?: number | null;
      evidence?: string[];
      inside_outside_hint?: string;
    } | null;
    validationSummary?: {
      status?: string;
      checked_requirements?: string[];
      decision_summary_he?: string;
      violation_count?: number;
    } | null;
  } | null>(null);
  const abortValidationRef = useRef<AbortController | null>(null);
  const validationLogWrapRef = useRef<HTMLDivElement | null>(null);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [validationHistory, setValidationHistory] = useState<any[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [showRequirementsModal, setShowRequirementsModal] = useState(false);
  const [requirementsFilter, setRequirementsFilter] = useState<'all' | 'passed' | 'failed' | 'not_checked'>('all');

  const [imageLightbox, setImageLightbox] = useState<{ src: string; title: string } | null>(null);
  const [requirementInfoId, setRequirementInfoId] = useState<string | null>(null);

  const overallRequirementStatus = useMemo(
    () => (validationResult ? computeOverallRequirementStatus(validationResult) : {}),
    [validationResult]
  );

  const effectiveCoverageStats = useMemo(
    () => (validationResult ? calculateEffectiveCoverageStatistics(validationResult, overallRequirementStatus) : null),
    [validationResult, overallRequirementStatus]
  );

  const getRequirementFromCoverage = (reqId: string): any | null => {
    if (!validationResult?.coverage) return null;
    const fromDict = validationResult.coverage.requirements?.[reqId];
    if (fromDict) return fromDict;
    const byCat = validationResult.coverage.by_category || {};
    for (const reqs of Object.values(byCat)) {
      if (!Array.isArray(reqs)) continue;
      const found = reqs.find((r: any) => r?.requirement_id === reqId);
      if (found) return found;
    }
    return null;
  };

  const getRequirementBadgeVariant = (reqId: string): 'success' | 'error' | 'neutral' => {
    const s = overallRequirementStatus[reqId] || (getRequirementFromCoverage(reqId)?.status as RequirementStatus | undefined);
    if (s === 'passed') return 'success';
    if (s === 'failed') return 'error';
    return 'neutral';
  };

  useEffect(() => {
    const el = validationLogWrapRef.current;
    if (!el) return;
    // Keep the newest log lines visible.
    el.scrollTop = el.scrollHeight;
  }, [validationLive?.logs?.length]);
  
  const handleDecompositionComplete = (decompId: string) => {
    setDecompositionId(decompId);
    setStage('decomposition_review');
  };
  
  const handleApprovalComplete = async (params: { mode: 'segments' | 'full_plan'; approvedSegments: string[]; check_groups: string[] }) => {
    setStage('validation');
    setLastApprovedSegmentIds(params.approvedSegments || []);

    const totalToValidate = params.mode === 'full_plan' ? 1 : params.approvedSegments.length;
    setValidationProgress({
      total: totalToValidate,
      current: 0,
      currentSegment: 'מתחיל בדיקה...'
    });

    setValidationLive({
      segmentId: null,
      stage: 'starting',
      logs: [{ ts: Date.now(), line: 'Starting validation stream…' }],
      door31: null,
      segmentMeta: null,
      analysisSummary: null,
      doorFocusSummary: null,
      validationSummary: null,
    });

    // Abort any prior stream
    if (abortValidationRef.current) {
      try { abortValidationRef.current.abort(); } catch { /* ignore */ }
    }
    abortValidationRef.current = new AbortController();
    
    try {

      // Preload decomposition snapshot for segment image URLs.
      const decompResponse = await fetch(`/api/v1/decomposition/${decompositionId}`);
      if (!decompResponse.ok) throw new Error('Failed to fetch decomposition data');
      const decompData = await decompResponse.json();
      setDecompositionSnapshot(decompData);

      // Preselect a segment image immediately so the user sees *something* even before
      // the first stream event arrives.
      const firstSegmentId =
        params.mode === 'full_plan'
          ? 'full_plan'
          : (Array.isArray(params.approvedSegments) && params.approvedSegments.length > 0 ? params.approvedSegments[0] : null);
      if (firstSegmentId) {
        const seg = (decompData?.segments || []).find((s: any) => s?.segment_id === firstSegmentId);
        setValidationLive((prev) => ({
          ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
          segmentId: String(firstSegmentId),
          stage: 'waiting_stream',
          segmentMeta: {
            title: seg?.title,
            type: seg?.type,
            description: seg?.description,
          },
        }));
      }

      const response = await fetch('/api/v1/segments/validate-segments-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decomposition_id: decompositionId,
          approved_segment_ids: params.approvedSegments,
          mode: params.mode,
          demo_mode: DEMO_MODE,
          check_groups: params.check_groups,
        }),
        signal: abortValidationRef.current.signal,
      });

      if (!response.ok || !response.body) throw new Error('Validation failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      const appendLog = (line: string) => {
        setValidationLive((prev) => {
          const next = prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null };
          const logs = [...next.logs, { ts: Date.now(), line }];
          // Keep last 80 lines
          const trimmed = logs.length > 80 ? logs.slice(logs.length - 80) : logs;
          return { ...next, logs: trimmed };
        });
      };

      const handleEvent = (evt: any) => {
        const type = String(evt?.event || 'unknown');

        if (type === 'stream_open') {
          setValidationLive((prev) => ({
            ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
            stage: 'stream_open',
          }));
          appendLog('stream_open: connected');
          return;
        }
        if (type === 'start') {
          setValidationLive((prev) => ({
            ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
            stage: 'started',
          }));
          appendLog(`start: total_segments=${evt.total_segments}`);
          return;
        }
        if (type === 'config') {
          appendLog(`config: check_groups=${(evt.check_groups || []).join(', ')}`);
          return;
        }
        if (type === 'segment_start') {
          const seg = (decompData?.segments || []).find((s: any) => s?.segment_id === evt.segment_id);
          setValidationProgress((prev) => ({
            total: prev?.total ?? evt.total ?? 0,
            current: Math.max(0, Number(evt.current || 0) - 1),
            currentSegment: `בודק ${evt.segment_id}…`,
          }));
          setValidationLive((prev) => ({
            ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
            segmentId: String(evt.segment_id || ''),
            stage: 'segment_start',
            door31: null,
            segmentMeta: {
              title: seg?.title,
              type: seg?.type ?? evt.segment_type,
              description: seg?.description ?? evt.description,
            },
            analysisSummary: null,
            doorFocusSummary: null,
            validationSummary: null,
          }));
          appendLog(`segment_start: ${evt.segment_id}`);
          return;
        }
        if (type === 'analysis_start') {
          setValidationProgress((prev) => {
            if (!prev) return prev;
            return { ...prev, currentSegment: `מנתח ${evt.segment_id || ''}…` };
          });
          appendLog(`analysis_start: ${evt.segment_id}`);
          return;
        }
        if (type === 'analysis_done') {
          setValidationProgress((prev) => {
            if (!prev) return prev;
            return { ...prev, currentSegment: `סיים ניתוח ${evt.segment_id || ''}` };
          });
          appendLog(`analysis_done: text=${evt.text_items}, dims=${evt.dimensions}, elems=${evt.structural_elements}`);
          return;
        }
        if (type === 'analysis_summary') {
          setValidationLive((prev) => ({
            ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
            analysisSummary: {
              primary_category: evt.primary_category,
              description_he: evt.description_he,
              explanation_he: evt.explanation_he,
              evidence: Array.isArray(evt.evidence) ? evt.evidence : undefined,
              relevant_requirements: Array.isArray(evt.relevant_requirements) ? evt.relevant_requirements : undefined,
            },
          }));
          appendLog(`analysis_summary: ${evt.primary_category || ''}`);
          return;
        }
        if (type === 'door_focus_start') {
          setValidationLive((prev) => ({
            ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
            stage: 'door_focus',
          }));
          setValidationProgress((prev) => {
            if (!prev) return prev;
            return { ...prev, currentSegment: `מזהה דלתות ומרווחים (3.1) בסגמנט ${evt.segment_id || ''}…` };
          });
          appendLog(`door_focus_start: ${evt.segment_id}`);
          return;
        }
        if (type === 'door_focus_done') {
          setValidationProgress((prev) => {
            if (!prev) return prev;
            return { ...prev, currentSegment: `סיים זיהוי דלתות (3.1) בסגמנט ${evt.segment_id || ''}` };
          });
          appendLog(`door_focus_done: doors=${evt.doors_found ?? 0}, best_conf=${evt.best_confidence ?? ''}`);
          return;
        }
        if (type === 'door_focus_summary') {
          setValidationLive((prev) => ({
            ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
            doorFocusSummary: {
              internal_clearance_cm: evt.internal_clearance_cm ?? null,
              external_clearance_cm: evt.external_clearance_cm ?? null,
              confidence: evt.confidence ?? null,
              evidence: Array.isArray(evt.evidence) ? evt.evidence : undefined,
              inside_outside_hint: evt.inside_outside_hint,
            },
          }));
          appendLog(`door_focus_summary: in=${evt.internal_clearance_cm ?? ''} out=${evt.external_clearance_cm ?? ''}`);
          return;
        }
        if (type === 'door_focus_error') {
          appendLog(`door_focus_error: ${evt.message || ''}`);
          return;
        }
        if (type === 'validation_start') {
          setValidationLive((prev) => ({
            ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
            stage: 'validation',
          }));
          setValidationProgress((prev) => {
            if (!prev) return prev;
            return { ...prev, currentSegment: `מריץ ולידציה על ${evt.segment_id || ''}…` };
          });
          appendLog(`validation_start: ${evt.segment_id}`);
          return;
        }
        if (type === 'validation_done') {
          setValidationProgress((prev) => ({
            total: prev?.total ?? 0,
            // Progress is advanced on `segment_done`; keep current unchanged here.
            current: Number(prev?.current ?? 0),
            currentSegment: `סיים ולידציה ${evt.segment_id} (${evt.status})`,
          }));
          if (evt.door_3_1) {
            setValidationLive((prev) => ({
              ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
              door31: evt.door_3_1,
            }));
          }
          appendLog(`validation_done: status=${evt.status}, checked=${(evt.checked_requirements || []).join(', ')}`);
          if (evt.door_3_1) {
            appendLog(`door 3.1: ${evt.door_3_1.status}${evt.door_3_1.reason_not_checked ? ' (' + evt.door_3_1.reason_not_checked + ')' : ''}`);
          }
          if (evt.decision_summary_he || typeof evt.violation_count === 'number') {
            setValidationLive((prev) => ({
              ...(prev ?? { segmentId: null, stage: 'starting', logs: [], door31: null }),
              validationSummary: {
                status: evt.status,
                checked_requirements: Array.isArray(evt.checked_requirements) ? evt.checked_requirements : undefined,
                decision_summary_he: evt.decision_summary_he,
                violation_count: typeof evt.violation_count === 'number' ? evt.violation_count : undefined,
              },
            }));
          }
          return;
        }
        if (type === 'segment_done') {
          setValidationProgress((prev) => ({
            total: prev?.total ?? evt.total ?? 0,
            current: Math.max(0, Math.min(Number(prev?.total ?? evt.total ?? 0), Number(evt.current ?? prev?.current ?? 0))),
            currentSegment: `הושלם ${evt.segment_id}`,
          }));
          appendLog(`segment_done: ${evt.segment_id} (${evt.current}/${evt.total})`);
          return;
        }
        if (type === 'segment_error') {
          appendLog(`segment_error: ${evt.segment_id} ${evt.message || ''}`);
          return;
        }
        if (type === 'error') {
          appendLog(`error: ${evt.message || ''}`);
          throw new Error(String(evt.message || 'Validation stream error'));
        }
        if (type === 'final') {
          appendLog('final: received result');
          const result = evt.result;
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
          return;
        }

        appendLog(`${type}: ${JSON.stringify(evt)}`);
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        // Process full lines
        while ((idx = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 1);
          if (!line) continue;
          try {
            const evt = JSON.parse(line);
            handleEvent(evt);
          } catch {
            // best-effort: show raw line
            appendLog(`raw: ${line.slice(0, 300)}`);
          }
        }
      }
      
    } catch (error) {
      console.error('Validation error:', error);
      alert('שגיאה בבדיקת הסגמנטים');
      setStage('decomposition_review');
    }
  };

  useEffect(() => {
    return () => {
      if (abortValidationRef.current) {
        try { abortValidationRef.current.abort(); } catch { /* ignore */ }
      }
    };
  }, []);

  const downloadJsonReport = () => {
    if (!validationResult) return;

    const report = {
      exported_at: new Date().toISOString(),
      demo_mode: Boolean(validationResult.demo_mode),
      demo_focus: validationResult.demo_focus || null,
      decomposition_id: decompositionId,
      selected_segment_ids: lastApprovedSegmentIds,
      decomposition: decompositionSnapshot,
      validation_result: validationResult,
    };

    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const safeId = (validationResult.validation_id || decompositionId || 'report')
      .toString()
      .replace(/[^a-zA-Z0-9-_]/g, '_');
    a.href = url;
    a.download = `mamad-report-${safeId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const openPrintableReport = () => {
    if (!validationResult) return;

    const effectiveStats = effectiveCoverageStats ?? calculateEffectiveCoverageStatistics(validationResult, overallRequirementStatus);

    const selectedIds = Array.isArray(lastApprovedSegmentIds) ? lastApprovedSegmentIds : [];
    const allSegments: any[] = Array.isArray(decompositionSnapshot?.segments) ? decompositionSnapshot.segments : [];
    const selectedSegments = selectedIds
      .map((id) => allSegments.find((s) => s.segment_id === id))
      .filter(Boolean);

    const analyzedSegments: any[] = Array.isArray(validationResult.segments)
      ? validationResult.segments
      : (Array.isArray(validationResult.analyzed_segments) ? validationResult.analyzed_segments : []);

    const esc = (v: any) => String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');

    const prettyJson = (obj: any) => esc(JSON.stringify(obj, null, 2));

    const coverage = validationResult.coverage || null;

    const apiVersion = 'v1';
    const fullPlanUrl = decompositionId
      ? `/api/${apiVersion}/decomposition/${encodeURIComponent(decompositionId)}/images/full-plan`
      : null;

    const getSegmentImageUrl = (segmentId: string) => {
      if (!decompositionId || !segmentId) return null;
      return `/api/${apiVersion}/decomposition/${encodeURIComponent(decompositionId)}/images/segments/${encodeURIComponent(segmentId)}`;
    };

    const html = `<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>דוח בדיקת ממ\"ד</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; color: #111827; }
    h1 { margin: 0 0 6px; font-size: 22px; }
    .muted { color: #6b7280; font-size: 12px; }
    .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px; margin: 12px 0; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .pill { display: inline-block; padding: 6px 10px; border-radius: 999px; border: 1px solid #e5e7eb; background: #f9fafb; font-size: 12px; }
    .img { max-width: 100%; height: auto; border: 1px solid #e5e7eb; border-radius: 10px; background: #fff; }
    .imgWrap { margin-top: 10px; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { border: 1px solid #e5e7eb; padding: 8px; vertical-align: top; font-size: 12px; }
    th { background: #f9fafb; text-align: right; }
    pre { white-space: pre-wrap; word-break: break-word; background: #f9fafb; border: 1px solid #e5e7eb; padding: 10px; border-radius: 10px; font-size: 11px; }
    .segment { page-break-inside: avoid; }
    @media print { body { margin: 12mm; } }
  </style>
</head>
<body>
  <h1>דוח בדיקת ממ\"ד</h1>
  <div class="muted">נוצר: ${esc(new Date().toLocaleString('he-IL'))}</div>

  <div class="card">
    <div class="row">
      <span class="pill">מזהה בדיקה: ${esc(validationResult.validation_id || '')}</span>
      <span class="pill">תאריך בדיקה: ${esc(new Date(validationResult.created_at || Date.now()).toLocaleString('he-IL'))}</span>
      <span class="pill">מזהה פירוק: ${esc(decompositionId || '')}</span>
      <span class="pill">סגמנטים שנותחו: ${esc(validationResult.total_segments ?? analyzedSegments.length ?? '')}</span>
      <span class="pill">דרישות שעברו: ${esc(effectiveStats.passed || 0)}</span>
      <span class="pill">אזהרות: ${esc(validationResult.warnings || 0)}</span>
    </div>
    ${validationResult.demo_mode ? `<div class="muted" style="margin-top:8px;"><strong>מצב דמו:</strong> מתמקדים בדרישות 1–3 (קירות, גובה/נפח, פתחים). ${esc(translateDemoFocusText(String(validationResult.demo_focus || '')))}</div>` : ''}
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px; font-size:16px;">תכנית מלאה</h2>
    ${fullPlanUrl ? `
      <div class="muted">תמונה באיכות מקורית (כפי שנשמרה במערכת). <a href="${esc(fullPlanUrl)}" target="_blank" rel="noopener">פתיחה בחלון חדש</a></div>
      <div class="imgWrap"><img class="img" src="${esc(fullPlanUrl)}" alt="תכנית מלאה" loading="lazy" /></div>
    ` : `<div class="muted">אין קישור לתכנית מלאה.</div>`}
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px; font-size:16px;">סגמנטים שנבחרו לבדיקה</h2>
    ${selectedSegments.length === 0 ? `<div class="muted">לא נמצאו פרטי סגמנטים (ייתכן שנפתח דוח מהיסטוריה).</div>` : ''}
    <table>
      <thead>
        <tr>
          <th>segment_id</th>
          <th>שם/כותרת</th>
          <th>סוג</th>
          <th>תיאור</th>
        </tr>
      </thead>
      <tbody>
        ${selectedSegments.map((s: any, idx: number) => {
          const vid = String(validationResult.validation_id || '').replace(/^val-/, '');
          const shortVid = vid ? vid.slice(0, 8) : '';
          const runDate = new Date(validationResult.created_at || Date.now()).toLocaleDateString('he-IL');
          const title = `בדיקה ${shortVid || '—'} · #${idx + 1} · ${runDate}`;
          const typeLabel = (!s?.type || String(s.type).toLowerCase() === 'unknown') ? 'ידני' : String(s.type);
          return `
          <tr>
            <td>${esc(s.segment_id)}</td>
            <td>${esc(title)}</td>
            <td>${esc(typeLabel)}</td>
            <td>${esc(s.description || '')}</td>
          </tr>
          `;
        }).join('')}
      </tbody>
    </table>
    ${selectedIds.length ? `<div class="muted" style="margin-top:8px;">סגמנטים שנבחרו: ${esc(selectedIds.join(', '))}</div>` : ''}
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px; font-size:16px;">תוצאות לפי סגמנט</h2>
    ${analyzedSegments.map((seg: any, idx: number) => {
      const analysis = seg.analysis_data || {};
      const classification = analysis.classification || {};
      const validation = seg.validation || {};
      const debug = validation.debug || {};
      const violations = Array.isArray(validation.violations) ? validation.violations : [];

      const vid = String(validationResult.validation_id || '').replace(/^val-/, '');
      const shortVid = vid ? vid.slice(0, 8) : '';
      const runDateTime = new Date(validationResult.created_at || Date.now()).toLocaleString('he-IL');

      const segImgUrl = getSegmentImageUrl(seg.segment_id);

      return `
        <div class="card segment">
          <div class="row">
            <span class="pill">#${idx + 1}</span>
            <span class="pill">בדיקה: ${esc(shortVid || (validationResult.validation_id || ''))}</span>
            <span class="pill">תאריך: ${esc(runDateTime)}</span>
            <span class="pill">segment_id: ${esc(seg.segment_id)}</span>
            <span class="pill">סטטוס: ${esc(seg.status || '')}</span>
            <span class="pill">passed: ${esc(Boolean(validation.passed))}</span>
          </div>

          <h3 style="margin:10px 0 6px; font-size:14px;">תמונה שנבדקה</h3>
          ${segImgUrl ? `
            <div class="muted">תמונה מלאה (לא thumbnail). <a href="${esc(segImgUrl)}" target="_blank" rel="noopener">פתיחה בחלון חדש</a></div>
            <div class="imgWrap"><img class="img" src="${esc(segImgUrl)}" alt="segment ${esc(seg.segment_id)}" loading="lazy" /></div>
          ` : `<div class="muted">אין קישור לתמונת הסגמנט.</div>`}

          <h3 style="margin:10px 0 6px; font-size:14px;">מידע שחולץ</h3>
          <pre>${prettyJson(analysis)}</pre>

          <h3 style="margin:10px 0 6px; font-size:14px;">בדיקות שהורצו</h3>
          <table>
            <tbody>
              <tr><th>primary_category</th><td>${esc(translateAnyCategory(String(classification.primary_category || debug.primary_category || '')))}</td></tr>
              <tr><th>categories_used</th><td>${esc(Array.isArray(debug.categories_used) ? debug.categories_used.map((c: any) => translateModelCategory(String(c))).join(', ') : '')}</td></tr>
              <tr><th>validators_run</th><td>${esc(Array.isArray(debug.validators_run) ? debug.validators_run.join(', ') : '')}</td></tr>
              <tr><th>checked_requirements</th><td>${esc(Array.isArray(validation.checked_requirements) ? validation.checked_requirements.join(', ') : '')}</td></tr>
              <tr><th>decision_summary</th><td>${esc(validation.decision_summary_he || '')}</td></tr>
            </tbody>
          </table>

          <h3 style="margin:10px 0 6px; font-size:14px;">הפרות</h3>
          ${violations.length === 0 ? `<div class="muted">אין הפרות.</div>` : `
            <table>
              <thead>
                <tr>
                  <th>rule_id</th>
                  <th>severity</th>
                  <th>קטגוריה</th>
                  <th>תיאור</th>
                  <th>דרישה</th>
                  <th>נמצא</th>
                </tr>
              </thead>
              <tbody>
                ${violations.map((v: any) => `
                  <tr>
                    <td>${esc(v.rule_id)}</td>
                    <td>${esc(v.severity)}</td>
                    <td>${esc(v.category)}</td>
                    <td>${esc(v.description)}</td>
                    <td>${esc(v.requirement)}</td>
                    <td>${esc(v.found)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          `}
        </div>
      `;
    }).join('')}
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px; font-size:16px;">כיסוי דרישות</h2>
    ${coverage ? `<pre>${prettyJson(coverage)}</pre>` : `<div class="muted">אין מידע כיסוי זמין.</div>`}
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px; font-size:16px;">Raw JSON (לשיתוף ולמידה)</h2>
    <pre>${prettyJson({
      exported_at: new Date().toISOString(),
      decomposition_id: decompositionId,
      selected_segment_ids: selectedIds,
      decomposition: decompositionSnapshot,
      validation_result: validationResult,
    })}</pre>
  </div>
</body>
</html>`;

    const w = window.open('', '_blank');
    if (!w) return;
    w.document.open();
    w.document.write(html);
    w.document.close();

    window.setTimeout(() => {
      try {
        w.focus();
        w.print();
      } catch {
        // ignore
      }
    }, 250);
  };
  
  const loadHistory = async () => {
    try {
      const response = await fetch('/api/v1/segments/validations');
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
  
  const loadValidationResults = async (validationId: string) => {
    console.log('Loading validation:', validationId);
    try {
      setIsLoadingHistory(true);
      
      // Load the validation results
      const response = await fetch(`/api/v1/segments/validation/${validationId}`);
      console.log('Validation response status:', response.status);
      
      if (!response.ok) throw new Error('Failed to load validation');
      
      const result = await response.json();
      console.log('Validation result:', result);
      
      // Enrich with segment data if decomposition_id exists
      if (result.decomposition_id) {
        const decompResponse = await fetch(`/api/v1/decomposition/${result.decomposition_id}`);
        if (decompResponse.ok) {
          const decompData = await decompResponse.json();
          setDecompositionSnapshot(decompData);
          setLastApprovedSegmentIds([]);
          
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
          setDecompositionId(result.decomposition_id);
        } else {
          setValidationResult(result);
        }
      } else {
        setValidationResult(result);
      }
      
      setStage('results');
    } catch (error) {
      console.error('Load validation error:', error);
      alert('שגיאה בטעינת תוצאות הבדיקה');
    } finally {
      setIsLoadingHistory(false);
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
    { number: 2, title: 'בחירה', description: 'בחירת אזורים בתכנית' },
    { number: 3, title: 'בדיקה', description: 'וולידציה מול תקנים' },
    { number: 4, title: 'תוצאות', description: 'דוח סופי' },
  ];

  const currentStepNumber = 
    stage === 'upload' ? 1 :
    stage === 'decomposition_review' ? 2 :
    stage === 'validation' ? 3 :
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
                    שמור על סדר עבודה: העלה קובץ, בחר אזורים לבדיקה, הרץ בדיקות וקבל דוח מפורט עם כיסוי תקנים.
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
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <Sparkles className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-text-primary">AI מתקדם</p>
                      <p className="text-xs text-text-muted mt-1">מופעל ע"י GPT-5.1</p>
                    </div>
                  </div>
                </Card>
                <div 
                  className="cursor-pointer"
                  onClick={() => {
                    console.log('Opening requirements modal...');
                    setShowRequirementsModal(true);
                  }}
                >
                  <Card 
                    padding="md" 
                    className="text-left hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start gap-4">
                      <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center shrink-0">
                        <BookOpen className="w-5 h-5 text-success" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-text-primary">66 דרישות</p>
                        <p className="text-xs text-text-muted mt-1">כל תקני ממ"ד</p>
                      </div>
                    </div>
                  </Card>
                </div>
                <Card padding="md" className="text-left hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
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
                בחר אזורים לבדיקה
              </h2>
              <p className="text-text-muted text-lg max-w-2xl mx-auto">
                גרור מלבנים על גבי התכנית כדי ליצור אזורים לבדיקה, אשר את האזורים הרצויים והמשך.
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

              {validationLive && (
                <div className="mt-8 space-y-4">
                  <div className="text-sm font-semibold text-text-primary">מה קורה עכשיו</div>
                  <div className="text-xs text-text-muted">
                    מצב: {String(validationLive.stage || 'starting')}
                    {validationLive.segmentId ? ` · סגמנט: ${String(validationLive.segmentId)}` : ' · ממתין להתחלת ניתוח הסגמנט הראשון…'}
                  </div>

                  <div className="text-sm font-semibold text-text-primary">סגמנט נבדק כעת</div>
                  <div className="rounded-lg border border-border bg-white p-3">
                    {(validationLive.segmentMeta?.title || validationLive.segmentMeta?.type || validationLive.segmentMeta?.description) && (
                      <div className="mb-3">
                        {validationLive.segmentMeta?.title && (
                          <div className="text-sm font-bold text-text-primary">{String(validationLive.segmentMeta.title)}</div>
                        )}
                        {(validationLive.segmentMeta?.type || validationLive.segmentMeta?.description) && (
                          <div className="text-xs text-text-muted">
                            {validationLive.segmentMeta?.type ? `סוג: ${String(validationLive.segmentMeta.type)}` : ''}
                            {validationLive.segmentMeta?.type && validationLive.segmentMeta?.description ? ' · ' : ''}
                            {validationLive.segmentMeta?.description ? String(validationLive.segmentMeta.description) : ''}
                          </div>
                        )}
                      </div>
                    )}
                    {validationLive.segmentId ? (
                      <img
                        src={
                          String(validationLive.segmentId) === 'full_plan'
                            ? `/api/v1/decomposition/${encodeURIComponent(String(decompositionId || ''))}/images/full-plan`
                            : `/api/v1/decomposition/${encodeURIComponent(String(decompositionId || ''))}/images/segments/${encodeURIComponent(String(validationLive.segmentId))}`
                        }
                        alt={`segment ${validationLive.segmentId}`}
                        className="w-full h-auto rounded-md border border-border"
                        loading="eager"
                        fetchPriority="high"
                      />
                    ) : (
                      <div className="text-xs text-text-muted">
                        ממתין לנתוני סטרים מהשרת… אם זה נתקע, בדוק שהשרת פעיל ושאין שגיאות ברשת.
                      </div>
                    )}
                  </div>

                  {validationLive.analysisSummary && (
                    <div className="rounded-lg border border-border bg-white p-3">
                      <div className="text-sm font-semibold text-text-primary">מה המודל זיהה (סיכום)</div>
                      <div className="text-xs text-text-muted mt-1">
                        {validationLive.analysisSummary.primary_category ? `קטגוריה: ${translateModelCategory(String(validationLive.analysisSummary.primary_category))}` : ''}
                        {validationLive.analysisSummary.relevant_requirements?.length
                          ? ` · דרישות רלוונטיות: ${validationLive.analysisSummary.relevant_requirements.join(', ')}`
                          : ''}
                      </div>
                      {validationLive.analysisSummary.description_he && (
                        <div className="text-sm text-text-primary mt-2">{String(validationLive.analysisSummary.description_he)}</div>
                      )}
                      {validationLive.analysisSummary.explanation_he && (
                        <div className="text-xs text-text-muted mt-2">{String(validationLive.analysisSummary.explanation_he)}</div>
                      )}
                      {validationLive.analysisSummary.evidence?.length ? (
                        <div className="mt-2 text-xs text-text-muted">
                          {(validationLive.analysisSummary.evidence || []).slice(0, 4).map((e, i) => (
                            <div key={i}>• {e}</div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  )}

                  {validationLive.doorFocusSummary && (
                    <div className="rounded-lg border border-border bg-white p-3">
                      <div className="text-sm font-semibold text-text-primary">מרווחי דלת (3.1) — ממצאים</div>
                      <div className="text-xs text-text-muted mt-1">
                        פנימי: {validationLive.doorFocusSummary.internal_clearance_cm ?? '—'} ס"מ · חיצוני: {validationLive.doorFocusSummary.external_clearance_cm ?? '—'} ס"מ
                        {typeof validationLive.doorFocusSummary.confidence === 'number' ? ` · ביטחון: ${Math.round(validationLive.doorFocusSummary.confidence * 100)}%` : ''}
                      </div>
                      {validationLive.doorFocusSummary.inside_outside_hint && (
                        <div className="text-xs text-text-muted mt-2">{String(validationLive.doorFocusSummary.inside_outside_hint)}</div>
                      )}
                      {validationLive.doorFocusSummary.evidence?.length ? (
                        <div className="mt-2 text-xs text-text-muted">
                          {(validationLive.doorFocusSummary.evidence || []).slice(0, 4).map((e, i) => (
                            <div key={i}>• {e}</div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  )}

                  {validationLive.door31 && (
                    <div className="text-xs text-text-muted">
                      דלת 3.1: {String(validationLive.door31.status || '')}{validationLive.door31.reason_not_checked ? ` (${String(validationLive.door31.reason_not_checked)})` : ''}
                    </div>
                  )}

                  {validationLive.validationSummary && (
                    <div className="rounded-lg border border-border bg-white p-3">
                      <div className="text-sm font-semibold text-text-primary">תוצאת בדיקה (סיכום)</div>
                      <div className="text-xs text-text-muted mt-1">
                        סטטוס: {String(validationLive.validationSummary.status || '')}
                        {typeof validationLive.validationSummary.violation_count === 'number' ? ` · חריגות: ${validationLive.validationSummary.violation_count}` : ''}
                      </div>
                      {validationLive.validationSummary.decision_summary_he && (
                        <div className="text-xs text-text-muted mt-2">{translateDemoFocusText(String(validationLive.validationSummary.decision_summary_he))}</div>
                      )}
                    </div>
                  )}

                  <div className="text-sm font-semibold text-text-primary">לוג בזמן אמת</div>
                  <div ref={validationLogWrapRef} className="rounded-lg border border-border bg-white p-3 max-h-56 overflow-auto">
                    <pre className="text-[11px] leading-5 text-text-muted whitespace-pre-wrap wrap-break-word">
                      {(validationLive.logs || []).map((l) => `${new Date(l.ts).toLocaleTimeString('he-IL')}  ${l.line}`).join('\n')}
                    </pre>
                  </div>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* Results Stage */}
        {stage === 'results' && validationResult && (
          <div className="max-w-7xl mx-auto space-y-10">
            {/* Success Header */}
            <Card padding="lg" className="bg-linear-to-r from-success/5 via-white to-primary/5 border-border shadow-sm">
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
                <div className="flex flex-wrap gap-3 items-center justify-end">
                  <Badge variant={((effectiveCoverageStats?.passed || 0) > 0) ? 'success' : 'neutral'}>
                    עברו {effectiveCoverageStats?.passed || 0} בדיקות
                  </Badge>
                  <Badge variant="info">{validationResult.total_segments} סגמנטים נותחו</Badge>
                  <Badge variant="warning">{validationResult.warnings || 0} אזהרות</Badge>

                  <div className="h-6 w-px bg-border mx-1 hidden sm:block" />

                  <Button
                    variant="outline"
                    size="sm"
                    icon={<FileText className="w-4 h-4" />}
                    onClick={openPrintableReport}
                    title="פותח חלון הדפסה (שמור כ-PDF)"
                  >
                    ייצוא PDF
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    icon={<Download className="w-4 h-4" />}
                    onClick={downloadJsonReport}
                    title="מוריד JSON מלא לשיתוף/למידה"
                  >
                    ייצוא JSON
                  </Button>
                </div>
              </div>
            </Card>

            {validationResult.demo_mode && (
              <Card padding="md" className="bg-primary/5 border border-primary/10">
                <div className="text-sm text-text-primary font-medium">
                  מצב דמו: מתמקדים בדרישות 1–3 (קירות, גובה/נפח, פתחים) כדי לקצר זמן ריצה.
                </div>
                {validationResult.demo_focus && (
                  <div className="text-xs text-text-muted mt-1">{translateDemoFocusText(String(validationResult.demo_focus))}</div>
                )}
              </Card>
            )}

            <div className="grid gap-8 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-6">
                {/* Analyzed Segments Section */}
                {validationResult.segments && validationResult.segments.length > 0 && (
                  <Card padding="lg" className="shadow-md border-border">
                    <h3 className="text-xl font-bold text-text-primary mb-6">
                      סגמנטים שנותחו ({validationResult.segments.length})
                    </h3>
                    
                    <div className="space-y-6">
                      {validationResult.segments.map((segment: any, idx: number) => {
                        const analysis = segment.analysis_data || {};
                        const classification = analysis.classification || {};
                        const validation = segment.validation || {};

                        const rawViolations: any[] = Array.isArray(validation?.violations) ? validation.violations : [];
                        const filteredViolations = rawViolations.filter((v: any) => {
                          const rid = normalizeRequirementId(v?.rule_id);
                          if (!rid) return true;
                          return overallRequirementStatus[rid] !== 'passed';
                        });

                        const checkedReqs: string[] = Array.isArray(validation.checked_requirements)
                          ? (validation.checked_requirements as string[])
                          : [];
                        const checksPerformed = Boolean((validation as any)?.checks_performed) || checkedReqs.length > 0;
                        const checksAttempted =
                          Boolean((validation as any)?.checks_attempted) ||
                          Array.isArray((validation as any)?.requirement_evaluations);
                        
                        // Determine segment status
                        const hasRelevantRequirements = classification.relevant_requirements && classification.relevant_requirements.length > 0;
                        const isNotApplicable = segment.status === 'analyzed' && !hasRelevantRequirements;
                        const isNotChecked =
                          segment.status === 'analyzed' &&
                          !checksPerformed &&
                          (validation.status === 'not_checked' || validation.status === 'skipped');
                        const isSuccess =
                          segment.status === 'analyzed' &&
                          checksPerformed &&
                          (String(validation.status || '').toLowerCase() === 'passed' || Boolean(validation.passed)) &&
                          filteredViolations.length === 0;
                        const isFailed =
                          segment.status === 'analyzed' &&
                          (String(validation.status || '').toLowerCase() === 'failed' || filteredViolations.length > 0);
                        const isError = segment.status === 'error';
                        
                        return (
                          <div 
                            key={segment.segment_id || idx} 
                            className={`border rounded-xl overflow-hidden ${
                              isSuccess ? 'border-success/30' : 
                              isError ? 'border-error/30' :
                              isNotApplicable ? 'border-blue-200' :
                              'border-border'
                            }`}
                          >
                            {/* Segment Header */}
                            <div className={`px-5 py-4 border-b flex items-start gap-4 ${
                              isSuccess ? 'bg-success/5 border-success/20' :
                              isError ? 'bg-error/5 border-error/20' :
                              isNotApplicable ? 'bg-blue-50 border-blue-200' :
                              'bg-gray-50 border-border'
                            }`}>
                              {/* Thumbnail */}
                              {(segment.thumbnail_url || segment.blob_url) && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    const src = String(segment.blob_url || segment.thumbnail_url);
                                    setImageLightbox({
                                      src,
                                      title: segment.title || segment.segment_id || `סגמנט ${idx + 1}`,
                                    });
                                  }}
                                  className="w-24 h-24 rounded-lg border border-border shadow-sm overflow-hidden bg-white hover:shadow-md transition-shadow focus:outline-none focus:ring-2 focus:ring-primary/30"
                                  title="לחץ להגדלה"
                                >
                                  <img
                                    src={String(segment.thumbnail_url || segment.blob_url)}
                                    alt={`Segment ${idx + 1}`}
                                    className="w-full h-full object-cover"
                                  />
                                </button>
                              )}
                              
                              <div className="flex-1">
                                <div className="flex items-start justify-between gap-3 mb-2">
                                  <div>
                                    <h4 className="font-semibold text-text-primary text-lg">
                                      {translateType(segment.type)}
                                    </h4>
                                    <p className="text-sm text-text-muted mt-1">
                                      {segment.description || translateType(segment.type)}
                                    </p>
                                  </div>
                                  
                                  {isSuccess && (
                                    <Badge variant="success">
                                      <CheckCircle2 className="w-4 h-4" />
                                      <span className="mr-1">עבר</span>
                                    </Badge>
                                  )}
                                  {isFailed && (
                                    <Badge variant="error">
                                      <AlertCircle className="w-4 h-4" />
                                      <span className="mr-1">נכשל</span>
                                    </Badge>
                                  )}
                                  {isNotChecked && (
                                    <Badge variant="neutral">
                                      <span className="mr-1">לא נבדק</span>
                                    </Badge>
                                  )}
                                  {isNotApplicable && (
                                    <Badge variant="neutral">
                                      <span className="mr-1">לא רלוונטי</span>
                                    </Badge>
                                  )}
                                  {isError && (
                                    <Badge variant="error">
                                      <AlertCircle className="w-4 h-4" />
                                      <span className="mr-1">שגיאה</span>
                                    </Badge>
                                  )}
                                  {!isSuccess && !isFailed && !isError && !isNotApplicable && !isNotChecked && (
                                    <Badge variant="warning">בדיקה</Badge>
                                  )}
                                </div>
                                
                                {/* Classification Info */}
                                {classification.primary_category && (
                                  <div className="mt-3 flex flex-wrap gap-2 items-center">
                                    <span className="text-xs text-text-muted">קטגוריה:</span>
                                    <Badge variant="neutral" size="sm">
                                      {translateAnyCategory(classification.primary_category)}
                                    </Badge>
                                    {classification.relevant_requirements && classification.relevant_requirements.length > 0 ? (
                                      <span className="text-xs text-text-muted">
                                        • {classification.relevant_requirements.length} דרישות רלוונטיות
                                      </span>
                                    ) : (
                                      <span className="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                                        • 0 דרישות רלוונטיות (סגמנט מידע)
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                            
                            {/* Analysis Details */}
                            <div className="p-5 space-y-4">
                              {/* Classification Transparency */}
                              {(() => {
                                const explanation = (classification as any)?.explanation_he;
                                const evidence = (classification as any)?.evidence as string[] | undefined;
                                const missing = (classification as any)?.missing_information as string[] | undefined;
                                const confidence = (classification as any)?.confidence as number | undefined;

                                if (!explanation && (!evidence || evidence.length === 0) && (!missing || missing.length === 0) && typeof confidence !== 'number') {
                                  return null;
                                }

                                return (
                                  <div>
                                    <h5 className="text-sm font-semibold text-text-primary mb-3">
                                      סיווג וחילוץ (שקיפות):
                                    </h5>
                                    <div className="bg-background/50 border border-border rounded-lg p-3 text-sm space-y-2">
                                      {typeof confidence === 'number' && (
                                        <div className="text-xs text-text-muted">
                                          <span className="font-semibold">ביטחון:</span>{' '}
                                          {(confidence * 100).toFixed(0)}%
                                        </div>
                                      )}
                                      {explanation && (
                                        <div>
                                          <span className="font-semibold">הסבר:</span>{' '}
                                          <span className="text-text-muted">{explanation}</span>
                                        </div>
                                      )}
                                      {Array.isArray(evidence) && evidence.length > 0 && (
                                        <div>
                                          <span className="font-semibold">ראיות:</span>{' '}
                                          <span className="text-text-muted">{evidence.join(' • ')}</span>
                                        </div>
                                      )}
                                      {Array.isArray(missing) && missing.length > 0 && (
                                        <div>
                                          <span className="font-semibold">חסר לולידציה:</span>{' '}
                                          <span className="text-text-muted">{missing.join(' • ')}</span>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })()}

                              {/* Requirements Checked */}
                              {(() => {
                                const checkedReqs: string[] =
                                  (segment?.analysis_data?.validation?.checked_requirements as string[] | undefined) ||
                                  (segment?.validation?.checked_requirements as string[] | undefined) ||
                                  (classification.relevant_requirements as string[] | undefined) ||
                                  [];

                                if (!checkedReqs || checkedReqs.length === 0) return null;

                                return (
                                  <div>
                                    <h5 className="text-sm font-semibold text-text-primary mb-3">
                                      דרישות שנבדקו:
                                    </h5>
                                    <div className="flex flex-wrap gap-2">
                                      {checkedReqs.map((reqId: string) => (
                                        <button
                                          key={reqId}
                                          type="button"
                                          onClick={() => setRequirementInfoId(reqId)}
                                          className="focus:outline-none focus:ring-2 focus:ring-primary/30 rounded-full"
                                          title="לחץ להסבר הבדיקה"
                                        >
                                          <Badge variant={getRequirementBadgeVariant(reqId)} size="sm">
                                            {reqId}
                                          </Badge>
                                        </button>
                                      ))}
                                    </div>
                                  </div>
                                );
                              })()}

                              {/* Validation Debug */}
                              {(() => {
                                const debug = (validation as any)?.debug;
                                const categoriesUsed = debug?.categories_used as string[] | undefined;

                                // Hide internal function names from end users; keep optional category list.
                                if (!categoriesUsed || categoriesUsed.length === 0) {
                                  return null;
                                }

                                return (
                                  <div>
                                    <h5 className="text-sm font-semibold text-text-primary mb-3">
                                      מה בוצע בולידציה:
                                    </h5>
                                    <div className="bg-background/50 border border-border rounded-lg p-3 text-sm space-y-2">
                                      {Array.isArray(categoriesUsed) && categoriesUsed.length > 0 && (
                                        <div>
                                          <span className="font-semibold">קטגוריות ששימשו:</span>{' '}
                                          <span className="text-text-muted">
                                            {categoriesUsed.map((c) => translateModelCategory(String(c))).join(', ')}
                                          </span>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })()}

                              {/* Why not checked (evidence-first) */}
                              {(() => {
                                const reqEvals: any[] = Array.isArray((validation as any)?.requirement_evaluations)
                                  ? ((validation as any).requirement_evaluations as any[])
                                  : [];

                                const isNotCheckedState =
                                  segment.status === 'analyzed' &&
                                  !checksPerformed &&
                                  (validation.status === 'not_checked' || validation.status === 'skipped' || !validation.status);

                                if (!isNotCheckedState) return null;

                                // If we have no structured evaluations, still show a helpful hint.
                                if (!reqEvals || reqEvals.length === 0) {
                                  if (!checksAttempted) return null;
                                  return (
                                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                                      <div className="flex items-start gap-3">
                                        <div className="w-5 h-5 bg-blue-100 rounded-full flex items-center justify-center shrink-0 mt-0.5">
                                          <span className="text-blue-600 text-xs font-bold">ℹ</span>
                                        </div>
                                        <div>
                                          <h5 className="text-sm font-semibold text-blue-900 mb-1">נוסו בדיקות אך לא הייתה הכרעה</h5>
                                          <p className="text-xs text-blue-700">השרת ניסה להריץ ולידציה, אבל לא נוצרו ראיות מסודרות לדרישות (requirement_evaluations ריק).</p>
                                        </div>
                                      </div>
                                    </div>
                                  );
                                }

                                const byReq: Record<string, any[]> = {};
                                for (const ev of reqEvals) {
                                  if (!ev || typeof ev !== 'object') continue;
                                  const rid = typeof ev.requirement_id === 'string' ? ev.requirement_id : null;
                                  if (!rid) continue;
                                  (byReq[rid] ||= []).push(ev);
                                }
                                const reqIds = Object.keys(byReq).sort();
                                if (reqIds.length === 0) return null;

                                return (
                                  <div>
                                    <h5 className="text-sm font-semibold text-text-primary mb-3">למה לא נבדק?</h5>
                                    <div className="space-y-2">
                                      {reqIds.map((rid) => {
                                        const items = byReq[rid] || [];
                                        const notCheckedItems = items.filter((x) => x?.status === 'not_checked');
                                        const sample = (notCheckedItems[0] || items[0]) as any;

                                        const reason = sample?.reason_not_checked ? String(sample.reason_not_checked) : '';
                                        const notesHe = sample?.notes_he ? String(sample.notes_he) : '';

                                        const evidenceTexts: string[] = [];
                                        const evidence = Array.isArray(sample?.evidence) ? sample.evidence : [];
                                        for (const e of evidence) {
                                          if (e && typeof e === 'object' && e.evidence_type === 'text' && typeof e.text === 'string' && e.text.trim()) {
                                            evidenceTexts.push(e.text.trim());
                                          }
                                        }

                                        return (
                                          <div key={rid} className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                                            <div className="flex items-start gap-2">
                                              <Badge variant="neutral" size="sm">{rid}</Badge>
                                              <div className="flex-1">
                                                <div className="text-xs text-blue-800 font-semibold">סטטוס: לא נבדק{reason ? ` (${reason})` : ''}</div>
                                                {notesHe && <div className="text-xs text-blue-700 mt-1">{notesHe}</div>}
                                                {evidenceTexts.length > 0 && (
                                                  <div className="text-xs text-blue-700 mt-1">ראיות/הקשר: {evidenceTexts.slice(0, 3).join(' • ')}</div>
                                                )}
                                              </div>
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                );
                              })()}
                                
                                {/* Validation Results */}
                                {filteredViolations.length > 0 && (
                                  <div>
                                    <h5 className="text-sm font-semibold text-error mb-3">
                                      בעיות שנמצאו ({filteredViolations.length}):
                                    </h5>
                                    <div className="space-y-2">
                                      {filteredViolations.map((violation: any, vIdx: number) => (
                                        <div 
                                          key={vIdx}
                                          className="bg-error/5 border border-error/20 rounded-lg p-3 text-sm"
                                        >
                                          <div className="flex items-start gap-2">
                                            <Badge variant="error" size="sm">{violation.rule_id}</Badge>
                                            <div className="flex-1">
                                              <p className="text-text-primary font-medium">
                                                {violation.description}
                                              </p>
                                              {violation.message && (
                                                <p className="text-text-muted text-xs mt-1">
                                                  {violation.message}
                                                </p>
                                              )}
                                            </div>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                
                                {/* Success Message with Details */}
                                {validation.passed && (!validation.violations || validation.violations.length === 0) && (
                                  <div className="space-y-3">
                                    {(() => {
                                      const checkedReqs: string[] = Array.isArray(validation?.checked_requirements)
                                        ? (validation.checked_requirements as string[])
                                        : [];

                                      const reqEvals: any[] = Array.isArray(validation?.requirement_evaluations)
                                        ? validation.requirement_evaluations
                                        : [];

                                      const debugPlannedReqs: string[] = Array.isArray(validation?.debug?.planned_requirements)
                                        ? (validation.debug.planned_requirements as string[])
                                        : [];

                                      const relevantReqs: string[] = Array.isArray(classification?.relevant_requirements)
                                        ? (classification.relevant_requirements as string[])
                                        : [];

                                      const attemptedReqs = Array.from(
                                        new Set(
                                          reqEvals
                                            .filter((e: any) => e && typeof e.requirement_id === 'string')
                                            .map((e: any) => e.requirement_id as string)
                                        )
                                      );

                                      const failedReqs = reqEvals
                                        .filter((e: any) => e && e.status === 'failed' && typeof e.requirement_id === 'string')
                                        .map((e: any) => e.requirement_id as string);

                                      const failedReqsFiltered = failedReqs.filter((rid: string) => overallRequirementStatus[rid] !== 'passed');

                                      // If nothing was actually checked, do not show a green success.
                                      if (checkedReqs.length === 0 && failedReqs.length === 0) {
                                        const showAttempted = attemptedReqs.length > 0;
                                        const reqsToShow = (debugPlannedReqs.length > 0 ? debugPlannedReqs : attemptedReqs);

                                        return (
                                          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                                            <div className="flex items-start gap-3">
                                              <div className="w-5 h-5 bg-blue-100 rounded-full flex items-center justify-center shrink-0 mt-0.5">
                                                <span className="text-blue-600 text-xs font-bold">ℹ</span>
                                              </div>
                                              <div>
                                                <h5 className="text-sm font-semibold text-blue-900 mb-1">
                                                  {showAttempted ? 'בוצעו ניסיונות בדיקה אך לא נמצאו ראיות מספיקות' : 'לא בוצעו בדיקות בפועל'}
                                                </h5>
                                                <p className="text-xs text-blue-700 mb-2">
                                                  הסגמנט סווג כ-<span className="font-semibold">"{translateType(segment.type)}"</span>{' '}
                                                  ({segment.description || translateType(segment.type)}),
                                                  {showAttempted
                                                    ? ' אך למרות זאת לא נמצאו ראיות מספיקות כדי לאמת אף דרישה בסגמנט הזה.'
                                                    : ' אך המערכת לא מצאה ראיות מספיקות כדי לאמת אף דרישה בסגמנט הזה.'}
                                                </p>
                                                {reqsToShow.length > 0 && (
                                                  <p className="text-xs text-blue-600">
                                                    <span className="font-semibold">דרישות שנוסו (לא בוצעו בפועל עקב חוסר ראיות):</span>{' '}
                                                    {reqsToShow.join(', ')}
                                                  </p>
                                                )}

                                                {!showAttempted && relevantReqs.length > 0 && (
                                                  <p className="text-xs text-blue-600 mt-1">
                                                    <span className="font-semibold">דרישות שסווגו כרלוונטיות (לאו דווקא נבדקו):</span>{' '}
                                                    {relevantReqs.join(', ')}
                                                  </p>
                                                )}
                                              </div>
                                            </div>
                                          </div>
                                        );
                                      }

                                      // If there are explicit failures (from evidence-first evaluations), show a failure summary.
                                      if (failedReqsFiltered.length > 0) {
                                        return (
                                          <div className="bg-error/5 border border-error/20 rounded-lg p-4">
                                            <div className="flex items-start gap-3">
                                              <AlertCircle className="w-5 h-5 text-error shrink-0 mt-0.5" />
                                              <div>
                                                <h5 className="text-sm font-semibold text-error mb-1">
                                                  נמצאו כשלים בדרישות שנבדקו
                                                </h5>
                                                <p className="text-xs text-text-muted">
                                                  דרישות שנכשלו: {failedReqsFiltered.join(', ')}
                                                </p>
                                              </div>
                                            </div>
                                          </div>
                                        );
                                      }

                                      // Success: checked requirements exist and none failed.
                                      return (
                                        <div className="bg-success/5 border border-success/20 rounded-lg p-4">
                                          <div className="flex items-start gap-3 mb-3">
                                            <CheckCircle2 className="w-5 h-5 text-success shrink-0 mt-0.5" />
                                            <div>
                                              <h5 className="text-sm font-semibold text-success mb-1">
                                                כל הבדיקות שבוצעו עברו בהצלחה!
                                              </h5>
                                              <p className="text-xs text-text-muted">
                                                בוצעו {checkedReqs.length} בדיקות בסגמנט זה
                                              </p>
                                            </div>
                                          </div>

                                          <div className="bg-white rounded-lg p-3 border border-success/10">
                                            <p className="text-xs text-text-muted font-semibold mb-2">
                                              ✓ הדרישות שנבדקו ועברו:
                                            </p>
                                            <div className="flex flex-wrap gap-2">
                                              {checkedReqs.map((reqId: string) => {
                                                const requirement = validationResult.coverage?.requirements?.[reqId];
                                                const variant = getRequirementBadgeVariant(reqId);
                                                return (
                                                  <div
                                                    key={reqId}
                                                    className="flex items-start gap-2 text-xs bg-success/5 border border-success/20 rounded-md px-2 py-1"
                                                    title={requirement?.description}
                                                  >
                                                    <button
                                                      type="button"
                                                      onClick={() => setRequirementInfoId(reqId)}
                                                      className="focus:outline-none focus:ring-2 focus:ring-primary/30 rounded-full"
                                                      title="לחץ להסבר הבדיקה"
                                                    >
                                                      <Badge variant={variant} size="sm" className="text-xs">
                                                        {reqId}
                                                      </Badge>
                                                    </button>
                                                    {requirement && (
                                                      <span className="text-text-muted max-w-xs truncate">
                                                        {requirement.description}
                                                      </span>
                                                    )}
                                                  </div>
                                                );
                                              })}
                                            </div>
                                          </div>
                                        </div>
                                      );
                                    })()}
                                  </div>
                                )}
                                
                                {/* LLM Reasoning */}
                                {(() => {
                                  const decisionSummary = segment?.validation?.decision_summary_he;

                                  // Do not display raw LLM reasoning/debug strings (often English/internal).
                                  if (!decisionSummary) return null;

                                  return (
                                    <details open className="text-sm mt-3 border-t border-border pt-3">
                                      <summary className="cursor-pointer text-text-primary hover:text-primary font-semibold mb-2">
                                        הסבר בדיקות
                                      </summary>
                                      {decisionSummary && (
                                        <div className="mt-2 text-text-muted bg-background rounded-lg p-3 border border-border text-sm leading-relaxed">
                                          {translateDemoFocusText(String(decisionSummary))}
                                        </div>
                                      )}
                                    </details>
                                  );
                                })()}
                              </div>
                            
                            {/* Error State */}
                            {segment.status === 'error' && (
                              <div className="p-5 bg-error/5 text-error text-sm">
                                <AlertCircle className="w-4 h-4 inline ml-2" />
                                שגיאה בניתוח הסגמנט: {segment.error || 'לא ידוע'}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </Card>
                )}
                
                {/* Coverage Report */}
                {validationResult.coverage && (
                  <Card padding="lg" className="shadow-md border-border">
                    <h3 className="text-xl font-bold text-text-primary mb-6">
                      כיסוי דרישות ממ״ד
                    </h3>
                    
                    {/* Coverage Statistics */}
                    <div className="bg-background rounded-xl p-6 mb-8 border border-border">
                      {(() => {
                        const stats = calculateEffectiveCoverageStatistics(validationResult, overallRequirementStatus);
                        return (
                          <>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                              <button
                                onClick={() => setRequirementsFilter('all')}
                                title="לחץ להצגת כל הדרישות"
                                className={`bg-white rounded-lg p-4 shadow-sm border transition-all cursor-pointer ${
                                  requirementsFilter === 'all' 
                                    ? 'border-primary ring-2 ring-primary/20' 
                                    : 'border-border hover:border-primary/50 hover:shadow-md'
                                }`}
                              >
                                <div className="text-3xl font-bold text-primary">
                                  {stats.coverage_percentage}%
                                </div>
                                <div className="text-xs text-text-muted mt-1 font-medium">כיסוי דרישות</div>
                              </button>
                              <button
                                onClick={() => setRequirementsFilter('passed')}
                                title="לחץ להצגת דרישות שעברו"
                                className={`bg-white rounded-lg p-4 shadow-sm border transition-all cursor-pointer ${
                                  requirementsFilter === 'passed' 
                                    ? 'border-success ring-2 ring-success/20' 
                                    : 'border-border hover:border-success/50 hover:shadow-md'
                                }`}
                              >
                                <div className="text-3xl font-bold text-success">
                                  {stats.passed}
                                </div>
                                <div className="text-xs text-text-muted mt-1 font-medium">עברו בדיקה</div>
                              </button>
                              <button
                                onClick={() => setRequirementsFilter('failed')}
                                title="לחץ להצגת דרישות שנכשלו"
                                className={`bg-white rounded-lg p-4 shadow-sm border transition-all cursor-pointer ${
                                  requirementsFilter === 'failed' 
                                    ? 'border-error ring-2 ring-error/20' 
                                    : 'border-border hover:border-error/50 hover:shadow-md'
                                }`}
                              >
                                <div className="text-3xl font-bold text-error">
                                  {stats.failed}
                                </div>
                                <div className="text-xs text-text-muted mt-1 font-medium">נכשלו</div>
                              </button>
                              <button
                                onClick={() => setRequirementsFilter('not_checked')}
                                title="לחץ להצגת דרישות שלא נבדקו"
                                className={`bg-white rounded-lg p-4 shadow-sm border transition-all cursor-pointer ${
                                  requirementsFilter === 'not_checked' 
                                    ? 'border-gray-400 ring-2 ring-gray-400/20' 
                                    : 'border-border hover:border-gray-400/50 hover:shadow-md'
                                }`}
                              >
                                <div className="text-3xl font-bold text-text-muted">
                                  {stats.not_checked}
                                </div>
                                <div className="text-xs text-text-muted mt-1 font-medium">לא נבדקו</div>
                              </button>
                            </div>
                            
                            <ProgressBar 
                              value={stats.coverage_percentage}
                              max={100}
                              color="violet"
                              size="lg"
                            />
                            <p className="text-center text-sm text-text-muted mt-3">
                              {stats.checked} מתוך {stats.total_requirements} דרישות נבדקו
                            </p>
                          </>
                        );
                      })()}
                    </div>
                    
                    {/* Requirements by Category */}
                    <div className="space-y-4 mb-8">
                      <div className="flex items-center justify-between">
                        <h4 className="text-lg font-semibold text-text-primary">
                          דרישות לפי קטגוריה
                          {requirementsFilter !== 'all' && (
                            <span className="text-sm font-normal text-text-muted mr-2">
                              (מסנן: {
                                requirementsFilter === 'passed' ? 'עברו בדיקה' :
                                requirementsFilter === 'failed' ? 'נכשלו' :
                                'לא נבדקו'
                              })
                            </span>
                          )}
                        </h4>
                        {requirementsFilter !== 'all' && (
                          <button
                            onClick={() => setRequirementsFilter('all')}
                            className="text-xs text-primary hover:text-primary/80 font-medium underline"
                          >
                            הצג הכל
                          </button>
                        )}
                      </div>
                      {(() => {
                        const filteredCategories = Object.entries(validationResult.coverage.by_category || {})
                          .map(([category, requirements]: [string, any]) => {
                            const enhancedRequirements = requirements.map((req: any) => {
                              const reqId = String(req?.requirement_id || '');
                              const effectiveStatus = overallRequirementStatus[reqId] || (req?.status as RequirementStatus | undefined) || 'not_checked';
                              return { ...req, status: effectiveStatus };
                            });
                            // Filter requirements based on selected filter
                            const filteredRequirements = enhancedRequirements.filter((req: any) => {
                              if (requirementsFilter === 'all') return true;
                              if (requirementsFilter === 'passed') return req.status === 'passed';
                              if (requirementsFilter === 'failed') return req.status === 'failed';
                              if (requirementsFilter === 'not_checked') return req.status === 'not_checked';
                              return true;
                            });

                            return { category, filteredRequirements };
                          })
                          .filter(({ filteredRequirements }) => filteredRequirements.length > 0);

                        if (filteredCategories.length === 0) {
                          return (
                            <div className="bg-gray-50 border border-border rounded-xl p-8 text-center">
                              <p className="text-text-muted">
                                לא נמצאו דרישות עבור הפילטר: {
                                  requirementsFilter === 'passed' ? 'עברו בדיקה' :
                                  requirementsFilter === 'failed' ? 'נכשלו' :
                                  'לא נבדקו'
                                }
                              </p>
                            </div>
                          );
                        }

                        return filteredCategories.map(({ category, filteredRequirements }) => (
                          <div key={category} className="border border-border rounded-xl overflow-hidden">
                            <div className="bg-gray-50 px-5 py-3 border-b border-border">
                              <h5 className="font-semibold text-text-primary">
                                {category}
                                <span className="text-xs font-normal text-text-muted mr-2">
                                  ({filteredRequirements.length} דרישות)
                                </span>
                              </h5>
                            </div>
                            <div className="divide-y divide-border">
                              {filteredRequirements.map((req: any) => (
                                <RequirementItem key={req.requirement_id} req={req} />
                              ))}
                            </div>
                          </div>
                        ));
                      })()}
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
                      label="סגמנטים שעברו"
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
                  כל הבדיקות שבוצעו עד כה - לחץ על בדיקה כדי לראות את התוצאות
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
            
            {isLoadingHistory && (
              <Card padding="lg" className="mb-6">
                <div className="flex items-center justify-center gap-3 text-primary">
                  <Loader2 className="w-6 h-6 animate-spin" />
                  <span className="font-medium">טוען תוצאות...</span>
                </div>
              </Card>
            )}
            
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
                {validationHistory.map((validation: any) => (
                  <div
                    key={validation.id || validation.validation_id}
                    onClick={() => {
                      console.log('Card clicked! Validation ID:', validation.id);
                      loadValidationResults(validation.id);
                    }}
                    className="cursor-pointer"
                  >
                    <Card 
                      hover 
                      padding="md"
                      className="transition-all hover:shadow-lg hover:border-primary/30"
                    >
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
                          <p className="text-xs text-text-muted/60 font-mono">
                            ID: {validation.id?.substring(0, 12)}...
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
                          {validation.total_segments || 0} סגמנטים
                        </span>
                      </div>
                    </div>
                  </Card>
                  </div>
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

      {/* Requirements Modal */}
      <RequirementsModal 
        isOpen={showRequirementsModal} 
        onClose={() => setShowRequirementsModal(false)} 
      />

      {/* Segment Image Lightbox */}
      {imageLightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          onClick={() => setImageLightbox(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[92vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 border-b border-border flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-text-primary truncate">{imageLightbox.title}</div>
                <div className="text-xs text-text-muted">לחץ על הרקע כדי לסגור</div>
              </div>
              <Button variant="outline" size="sm" onClick={() => setImageLightbox(null)}>
                סגור
              </Button>
            </div>
            <div className="p-4 overflow-auto bg-background">
              <div className="flex justify-end mb-3">
                <a
                  href={imageLightbox.src}
                  target="_blank"
                  rel="noopener"
                  className="text-xs text-primary hover:text-primary/80 font-medium underline"
                >
                  פתיחה בחלון חדש
                </a>
              </div>
              <img
                src={imageLightbox.src}
                alt={imageLightbox.title}
                className="w-full h-auto rounded-lg border border-border bg-white"
              />
            </div>
          </div>
        </div>
      )}

      {/* Requirement Info Modal */}
      {requirementInfoId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          onClick={() => setRequirementInfoId(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {(() => {
              const rid = requirementInfoId;
              const req = rid ? getRequirementFromCoverage(rid) : null;
              const status = rid ? (overallRequirementStatus[rid] || (req?.status as RequirementStatus | undefined) || 'not_checked') : 'not_checked';
              const statusHe = status === 'passed' ? 'עבר' : status === 'failed' ? 'נכשל' : 'לא נבדק';
              const desc = String(req?.description || '');
              const simple = toSimpleOneLiner(desc);

              return (
                <>
                  <div className="px-6 py-4 border-b border-border flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Badge variant={getRequirementBadgeVariant(rid)} size="md">
                        {rid}
                      </Badge>
                      <div>
                        <div className="text-sm font-semibold text-text-primary">הסבר בדיקה</div>
                        <div className="text-xs text-text-muted">סטטוס כללי: {statusHe}</div>
                      </div>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setRequirementInfoId(null)}>
                      סגור
                    </Button>
                  </div>
                  <div className="p-6 overflow-auto space-y-4">
                    <div className="bg-background border border-border rounded-lg p-4">
                      <div className="text-xs font-semibold text-text-primary mb-1">במילים פשוטות</div>
                      <div className="text-sm text-text-muted leading-relaxed">{simple}</div>
                    </div>

                    <div>
                      <div className="text-xs font-semibold text-text-primary mb-2">תיאור הבדיקה (כפי שמוגדר במערכת)</div>
                      <div className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
                        {desc || 'אין תיאור זמין לדרישה זו.'}
                      </div>
                    </div>

                    {Array.isArray(req?.segments_checked) && req.segments_checked.length > 0 && (
                      <div>
                        <div className="text-xs font-semibold text-text-primary mb-2">אומת/נבדק בסגמנטים</div>
                        <div className="flex flex-wrap gap-2">
                          {req.segments_checked.map((s: string, i: number) => (
                            <Badge key={`${s}-${i}`} variant="neutral" size="sm">{s}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
