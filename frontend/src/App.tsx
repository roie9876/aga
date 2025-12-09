import { useState } from 'react';
import { Upload, CheckCircle, XCircle, AlertTriangle, FileText, Loader2 } from 'lucide-react';
import type { ValidationResponse } from './types';

const API_BASE_URL = 'http://localhost:8000';

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string>('test-project-001');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setResult(null);
      setError(null);
      
      // Create preview
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result as string);
      };
      reader.readAsDataURL(selectedFile);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && (droppedFile.type.startsWith('image/') || droppedFile.type === 'application/pdf')) {
      setFile(droppedFile);
      setResult(null);
      setError(null);
      
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result as string);
      };
      reader.readAsDataURL(droppedFile);
    }
  };

  const handleValidate = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('project_id', projectId);

      const response = await fetch(`${API_BASE_URL}/api/v1/validate`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Validation failed');
      }

      const uploadResponse = await response.json();
      const validationId = uploadResponse.validation_id;

      // Fetch the full validation results
      const resultsResponse = await fetch(`${API_BASE_URL}/api/v1/results/${validationId}`);
      
      if (!resultsResponse.ok) {
        throw new Error('Failed to fetch validation results');
      }

      const data: ValidationResponse = await resultsResponse.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (passed: boolean) => {
    return passed ? (
      <CheckCircle className="w-5 h-5 text-green-500" />
    ) : (
      <XCircle className="w-5 h-5 text-red-500" />
    );
  };

  const getOverallStatusColor = (status: string) => {
    switch (status) {
      case 'passed':
        return 'bg-green-100 text-green-800 border-green-300';
      case 'failed':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'warning':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  return (
    <div className="min-h-screen py-8 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">
            בדיקת תוכנית ממ״ד
          </h1>
          <p className="text-white/80 text-lg">
            Mamad (Protected Space) Plan Validator
          </p>
          <p className="text-white/60 text-sm mt-2">
            Powered by Azure OpenAI GPT-5.1 with Reasoning
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Upload Section */}
          <div className="bg-white rounded-lg shadow-xl p-6">
            <h2 className="text-2xl font-semibold mb-4 flex items-center gap-2">
              <Upload className="w-6 h-6" />
              Upload Plan
            </h2>

            {/* Project ID Input */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Project ID
              </label>
              <input
                type="text"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                placeholder="Enter project ID"
              />
            </div>

            {/* Drag & Drop Area */}
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-purple-500 transition-colors cursor-pointer"
            >
              <input
                type="file"
                id="file-input"
                onChange={handleFileSelect}
                accept="image/*,application/pdf"
                className="hidden"
              />
              <label htmlFor="file-input" className="cursor-pointer">
                <FileText className="w-16 h-16 mx-auto mb-4 text-gray-400" />
                <p className="text-gray-600 mb-2">
                  Drag & drop your plan here, or click to browse
                </p>
                <p className="text-sm text-gray-400">
                  Supports: PDF, PNG, JPG, DWG
                </p>
              </label>
            </div>

            {/* Preview */}
            {preview && (
              <div className="mt-4">
                <p className="text-sm font-medium text-gray-700 mb-2">Preview:</p>
                <img
                  src={preview}
                  alt="Plan preview"
                  className="w-full h-64 object-contain border border-gray-200 rounded-lg bg-gray-50"
                />
                <p className="text-sm text-gray-600 mt-2">
                  File: {file?.name}
                </p>
              </div>
            )}

            {/* Validate Button */}
            <button
              onClick={handleValidate}
              disabled={!file || loading}
              className="w-full mt-6 bg-gradient-to-r from-purple-600 to-indigo-600 text-white py-3 px-6 rounded-lg font-semibold hover:from-purple-700 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Validating...
                </>
              ) : (
                <>
                  <CheckCircle className="w-5 h-5" />
                  Validate Plan
                </>
              )}
            </button>

            {/* Error Message */}
            {error && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-red-800 text-sm">{error}</p>
              </div>
            )}
          </div>

          {/* Results Section */}
          <div className="bg-white rounded-lg shadow-xl p-6">
            <h2 className="text-2xl font-semibold mb-4 flex items-center gap-2">
              <FileText className="w-6 h-6" />
              Validation Results
            </h2>

            {!result && !loading && (
              <div className="text-center py-12 text-gray-400">
                <AlertTriangle className="w-16 h-16 mx-auto mb-4" />
                <p>Upload and validate a plan to see results</p>
              </div>
            )}

            {loading && (
              <div className="text-center py-12">
                <Loader2 className="w-16 h-16 mx-auto mb-4 text-purple-600 animate-spin" />
                <p className="text-gray-600">Analyzing plan with GPT-5.1...</p>
                <p className="text-sm text-gray-400 mt-2">This may take 30-90 seconds</p>
              </div>
            )}

            {result && (
              <div className="space-y-6">
                {/* Overall Status */}
                <div className={`p-4 rounded-lg border-2 ${getOverallStatusColor(result.status)}`}>
                  <h3 className="font-bold text-lg mb-1">
                    Overall Status: {result.status.toUpperCase()}
                  </h3>
                  <p className="text-sm">
                    {result.passed_checks}/{result.total_checks} checks passed
                  </p>
                  <p className="text-xs text-gray-600 mt-1">ID: {result.validation_id}</p>
                </div>

                {/* Extracted Data */}
                <div className="border border-gray-200 rounded-lg p-4">
                  <h3 className="font-semibold text-lg mb-3">Extracted Measurements</h3>
                  <div className="space-y-2 text-sm">
                    {result.extracted_data.external_wall_count && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">External Walls:</span>
                        <span className="font-medium">{result.extracted_data.external_wall_count}</span>
                      </div>
                    )}
                    {result.extracted_data.wall_thickness_cm && result.extracted_data.wall_thickness_cm.length > 0 && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">Wall Thickness:</span>
                        <span className="font-medium">{result.extracted_data.wall_thickness_cm.join(', ')} cm</span>
                      </div>
                    )}
                    {result.extracted_data.room_height_m && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">Room Height:</span>
                        <span className="font-medium">{result.extracted_data.room_height_m}m</span>
                      </div>
                    )}
                    {result.extracted_data.room_volume_m3 && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">Room Volume:</span>
                        <span className="font-medium">{result.extracted_data.room_volume_m3}m³</span>
                      </div>
                    )}
                    {result.extracted_data.confidence_score !== undefined && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">Confidence:</span>
                        <span className="font-medium">{(result.extracted_data.confidence_score * 100).toFixed(1)}%</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Validation Results */}
                <div className="border border-gray-200 rounded-lg p-4">
                  <h3 className="font-semibold text-lg mb-3">Validation Checks</h3>
                  {result.violations.length === 0 ? (
                    <div className="text-center py-8 text-green-600">
                      <CheckCircle className="w-12 h-12 mx-auto mb-2" />
                      <p className="font-medium">כל הבדיקות עברו בהצלחה!</p>
                      <p className="text-sm text-gray-600 mt-1">All validation checks passed</p>
                    </div>
                  ) : (
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                      {result.violations.map((violation, idx) => (
                        <div
                          key={idx}
                          className="p-3 rounded-lg border bg-red-50 border-red-200"
                        >
                          <div className="flex items-start gap-3">
                            <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                            <div className="flex-1">
                              <p className="font-medium text-sm mb-1" dir="rtl">
                                {violation.description}
                              </p>
                              {violation.message && (
                                <p className="text-xs text-gray-600 mt-1" dir="rtl">
                                  {violation.message}
                                </p>
                              )}
                              <div className="flex gap-4 mt-2 text-xs text-gray-500">
                                <span className="px-2 py-0.5 bg-red-100 rounded text-red-700">
                                  {violation.severity}
                                </span>
                                {violation.actual_value !== undefined && (
                                  <span>Actual: {JSON.stringify(violation.actual_value)}</span>
                                )}
                                {violation.expected_value !== undefined && (
                                  <span>Expected: {JSON.stringify(violation.expected_value)}</span>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Plan URL */}
                {result.plan_blob_url && (
                  <div className="text-xs text-gray-500">
                    <p>Plan: <span className="font-medium">{result.plan_name}</span></p>
                    <p className="mt-1">Stored at: <a href={result.plan_blob_url} target="_blank" rel="noopener noreferrer" className="text-purple-600 hover:underline break-all">{result.plan_blob_url}</a></p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
