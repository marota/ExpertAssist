import { describe, it, expect } from 'vitest';
import App from './App';

describe('Import Test', () => {
  it('imports App successfully', () => {
    expect(App).toBeDefined();
  });
});
