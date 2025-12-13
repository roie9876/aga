export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

// Decomposition types
export type SegmentType = 'floor_plan' | 'section' | 'detail' | 'elevation' | 'legend' | 'table' | 'unknown';

export type DecompositionStatus = 'processing' | 'analyzing' | 'cropping' | 'complete' | 'failed' | 'review_needed';

export interface ProjectMetadata {
  project_name?: string;
  architect?: string;
  date?: string;
  plan_number?: string;
  scale?: string;
  floor?: string;
  apartment?: string;
  additional_info?: Record<string, any>;
}

export interface PlanSegment {
  segment_id: string;
  type: SegmentType;
  title: string;
  description: string;
  bounding_box: BoundingBox;
  blob_url: string;
  thumbnail_url: string;
  confidence: number;
  llm_reasoning?: string;
  analysis_data?: any;
  approved_by_user: boolean;
  used_in_checks: string[];
  created_at: string;
}

export interface ProcessingStats {
  total_segments: number;
  processing_time_seconds: number;
  llm_tokens_used: number;
  conversion_time_seconds?: number;
  analysis_time_seconds?: number;
  cropping_time_seconds?: number;
}

export interface PlanDecomposition {
  id: string;
  validation_id: string;
  project_id: string;
  status: DecompositionStatus;
  full_plan_url: string;
  full_plan_width: number;
  full_plan_height: number;
  file_size_mb: number;
  metadata: ProjectMetadata;
  segments: PlanSegment[];
  processing_stats: ProcessingStats;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  error_message?: string;
}

export interface DecompositionResponse {
  decomposition_id: string;
  status: DecompositionStatus;
  estimated_time_seconds: number;
  message: string;
}

// Validation types

export interface ValidationViolation {
  rule_id: string;
  category: string;
  description: string;
  severity: string;
  expected_value?: any;
  actual_value?: any;
  message?: string;
  bounding_box?: BoundingBox | null;
  location_description?: string;
  section_reference?: string;
}

export interface IndividualCheck {
  check_id: string;
  check_name: string;
  description: string;
  status: 'pass' | 'fail' | 'skip';
  plan_image_url: string;
  bounding_box?: BoundingBox | null;
  violation?: ValidationViolation | null;
  reasoning?: string;
}

export interface ExtractedData {
  external_wall_count?: number;
  wall_thickness_cm?: number[];
  wall_with_window?: boolean;
  room_height_m?: number;
  room_volume_m3?: number;
  door_spacing_internal_cm?: number;
  door_spacing_external_cm?: number;
  window_spacing_cm?: number;
  window_to_door_spacing_cm?: number;
  has_ventilation_note?: boolean;
  has_air_inlet_pipe?: boolean;
  has_air_outlet_pipe?: boolean;
  concrete_type?: string;
  is_passage_between_rooms?: boolean;
  has_fixed_cabinets?: boolean;
  accessible_without_bathroom?: boolean;
  confidence_score?: number;
  reasoning?: string;
}

export interface ValidationResponse {
  validation_id: string;
  project_id: string;
  plan_name: string;
  plan_blob_url: string;
  status: 'pass' | 'fail' | 'needs_review';
  extracted_data: ExtractedData;
  checks: IndividualCheck[];
  violations: ValidationViolation[]; // Deprecated, use checks instead
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  created_at: string;
}

// Coverage tracking types
export interface RequirementCoverage {
  requirement_id: string;
  category: string;
  description: string;
  severity: 'critical' | 'error' | 'warning';
  status: 'passed' | 'failed' | 'not_checked';
  segments_checked: string[];
  violations: ValidationViolation[];
}

export interface CoverageStatistics {
  total_requirements: number;
  checked: number;
  passed: number;
  failed: number;
  not_checked: number;
  coverage_percentage: number;
  pass_percentage: number;
}

export interface MissingSegment {
  requirement_id: string;
  description: string;
  category: string;
  severity: string;
  needed_segment_type: string;
}

export interface CoverageReport {
  statistics: CoverageStatistics;
  requirements: Record<string, RequirementCoverage>;
  by_category: Record<string, RequirementCoverage[]>;
  missing_segments_needed: MissingSegment[];
}

