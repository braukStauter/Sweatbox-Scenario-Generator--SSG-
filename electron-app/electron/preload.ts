import { contextBridge, ipcRenderer } from 'electron';
import type {
  ScenarioConfig,
  ScenarioResult,
  VNASUploadResult,
} from '../shared/types';

contextBridge.exposeInMainWorld('ssg', {
  scenario: {
    generate: (config: ScenarioConfig): Promise<ScenarioResult> =>
      ipcRenderer.invoke('scenario:generate', config),
  },
  fs: {
    saveScenario: (filename: string, contents: string): Promise<string> =>
      ipcRenderer.invoke('fs:saveScenario', filename, contents),
    openScenario: (): Promise<{ filename: string; contents: string } | null> =>
      ipcRenderer.invoke('fs:openScenario'),
    loadConfig: (): Promise<unknown> => ipcRenderer.invoke('fs:loadConfig'),
  },
  airports: {
    list: () => ipcRenderer.invoke('airports:list'),
  },
  vnas: {
    upload: (scenarioContents: string): Promise<VNASUploadResult> =>
      ipcRenderer.invoke('vnas:upload', scenarioContents),
    reset: (): Promise<void> => ipcRenderer.invoke('vnas:reset'),
    clearCookies: (): Promise<void> => ipcRenderer.invoke('vnas:clearCookies'),
  },
  app: {
    checkForUpdates: (): Promise<{
      currentVersion: string;
      latestVersion: string | null;
      updateAvailable: boolean;
      releaseUrl: string;
      error?: string;
    }> => ipcRenderer.invoke('app:checkForUpdates'),
    openExternal: (url: string): Promise<void> =>
      ipcRenderer.invoke('app:openExternal', url),
  },
});
