export interface ValidationResult {
  rule_id: string;
  category: string;
  description: string;
  passed: boolean;
  actual_value?: any;
  expected_value?: any;
  message?: string;
  severity?: string;
}

export interface ExtractedData {
  wall_thickness?: number;
  wall_count?: number;
  room_dimensions?: {
    length?: number;
    width?: number;
    height?: number;
  };
  door_spacing?: number;
  window_spacing?: number;
  annotations?: string[];
  confidence_score?: number;
}

export interface ValidationResponse {
  validation_id: string;
  project_id: string;
  plan_url: string;
  extracted_data: ExtractedData;
  validation_results: ValidationResult[];
  overall_status: 'passed' | 'failed' | 'warning';
  created_at: string;
}
