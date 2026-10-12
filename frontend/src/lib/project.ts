/** Where the project lives. Change REPO_URL if you fork or move the repository. */
export const REPO_URL = "https://github.com/AR13X3/SiteScore";
export const CONTRIBUTING_URL = `${REPO_URL}/blob/main/CONTRIBUTING.md`;
export const ISSUES_URL = `${REPO_URL}/issues`;
export const OPENROUTER_KEYS_URL = "https://openrouter.ai/keys";

/** File on GitHub, for "edit this" links in the Data page. */
export const repoFile = (path: string) => `${REPO_URL}/blob/main/${path}`;
