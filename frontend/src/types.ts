export interface ValidationViolation {
  rule_id: string;
  category: string;
  description: string;
  severity: string;
  expected_value?: any;
  actual_value?: any;
  message?: string;
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
  violations: ValidationViolation[];
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  created_at: string;
}
