// Test file to verify imports work
import type { DecompositionResponse } from './types';

const test: DecompositionResponse = {
  decomposition_id: 'test',
  status: 'complete',
  estimated_time_seconds: 60,
  message: 'test'
};

console.log('Import works!', test);
