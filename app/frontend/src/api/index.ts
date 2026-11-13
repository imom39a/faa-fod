import { createHttpApi, type Api } from './client';

export const MOCK_MODE = import.meta.env.VITE_MOCK === '1';

/**
 * The API the app talks to. With VITE_MOCK=1 the in-browser mock backend is
 * loaded; otherwise the mock (and its fixture photos) is left out of the bundle.
 */
export async function loadApi(): Promise<Api> {
  if (import.meta.env.VITE_MOCK === '1') {
    const { createMockApi } = await import('../mock/mockApi');
    return createMockApi();
  }
  return createHttpApi();
}
