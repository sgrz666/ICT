import { average, grade } from './grading.js';

export function report(scores) {
  const mean = average(scores);
  return { mean, grade: grade(mean) };
}
