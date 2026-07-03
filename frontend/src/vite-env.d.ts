/**
 * src/vite-env.d.ts
 *
 * Vite client type declarations.
 * Adds type support for CSS module imports (*.module.css).
 */

/// <reference types="vite/client" />

declare module "*.module.css" {
  const classes: Record<string, string>;
  export default classes;
}
