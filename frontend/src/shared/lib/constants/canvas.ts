// frontend/src/constants/canvas.ts
// ADDED: Named constants for canvas coordinate system and UI dimensions

/**
 * # Canvas Coordinate System Specification
 * 
 * ## Three Coordinate Layers
 * 
 * 1. **World Space** (node_world_pos)
 *    - Absolute coordinates in the infinite canvas
 *    - Nodes are positioned in world space
 *    - Origin: (0, 0) at top-left of canvas
 * 
 * 2. **Viewport Space** (node_viewport_pos)
 *    - Coordinates relative to the visible viewport
 *    - Affected by pan offset
 *    - Formula: viewport_pos = world_pos + pan
 * 
 * 3. **Screen Space** (node_screen_pos)
 *    - Final pixel coordinates on the monitor
 *    - Affected by both pan and scale
 *    - Formula: screen_pos = (world_pos × scale) + pan
 * 
 * ## Invariants
 * 
 * - node_screen_pos = (node_world_pos × scale) + pan
 * - node_world_pos = (node_screen_pos - pan) / scale
 * - Scale bounds: VIEWPORT_SCALE_MIN ≤ scale ≤ VIEWPORT_SCALE_MAX
 * 
 * ## Visual Reference
 * 
 * ```
 * World Space:  [node] at (100, 200)
 *               ↓ × scale (1.5)
 * Viewport:     [node] at (150, 300)
 *               ↓ + pan (50, 100)
 * Screen:       [node] at (200, 400) pixels
 * ```
 */

// ==================== NODE DIMENSIONS ====================

/** Half width of a node in pixels (used for centering) */
export const NODE_HALF_WIDTH = 110;

/** Half height of a node in pixels (used for centering) */
export const NODE_HALF_HEIGHT = 40;

/** Full width of a node in pixels */
export const NODE_WIDTH = NODE_HALF_WIDTH * 2;

/** Full height of a node in pixels */
export const NODE_HEIGHT = NODE_HALF_HEIGHT * 2;

// ==================== VIEWPORT CONSTRAINTS ====================

/** Minimum zoom scale (20% zoom out) */
export const VIEWPORT_SCALE_MIN = 0.2;

/** Maximum zoom scale (300% zoom in) */
export const VIEWPORT_SCALE_MAX = 3.0;

/** Default zoom scale (100%) */
export const VIEWPORT_SCALE_DEFAULT = 1.0;

// ==================== ZOOM CONFIGURATION ====================

/** Zoom sensitivity factor for mouse wheel */
export const ZOOM_SENSITIVITY = 300;

/** Zoom factor per wheel step (1.1 = 10% per step) */
export const ZOOM_FACTOR = 1.1;

// ==================== PAN CONFIGURATION ====================

/** Mouse button for panning (1 = middle click) */
export const PAN_MOUSE_BUTTON = 1;

/** Alternative pan modifier key */
export const PAN_MODIFIER_KEY = 'Alt';

// ==================== SELECTION CONFIGURATION ====================

/** Distance in pixels for click detection on nodes */
export const NODE_CLICK_THRESHOLD = 5;

/** Connection port size in pixels */
export const CONNECTION_PORT_SIZE = 16;

// ==================== UI DIMENSIONS ====================

/** Width of the hamburger icon in pixels (used for offset calculations) */
export const SIDEBAR_HAMBURGER_WIDTH = 40;

/** Line height used in expanding textarea (pixels) */
export const TEXTAREA_LINE_HEIGHT = 24;

/** Maximum number of rows for textarea on desktop */
export const TEXTAREA_MAX_ROWS_DESKTOP = 15;

/** Maximum number of rows for textarea on mobile */
export const TEXTAREA_MAX_ROWS_MOBILE = 5;

/** Minimum height of textarea in pixels */
export const TEXTAREA_MIN_HEIGHT = 48;

// Export all constants as a single object for convenience
export const CANVAS_CONSTANTS = {
  NODE_HALF_WIDTH,
  NODE_HALF_HEIGHT,
  NODE_WIDTH,
  NODE_HEIGHT,
  VIEWPORT_SCALE_MIN,
  VIEWPORT_SCALE_MAX,
  VIEWPORT_SCALE_DEFAULT,
  ZOOM_SENSITIVITY,
  ZOOM_FACTOR,
  PAN_MOUSE_BUTTON,
  PAN_MODIFIER_KEY,
  NODE_CLICK_THRESHOLD,
  CONNECTION_PORT_SIZE,
  SIDEBAR_HAMBURGER_WIDTH,
  TEXTAREA_LINE_HEIGHT,
  TEXTAREA_MAX_ROWS_DESKTOP,
  TEXTAREA_MAX_ROWS_MOBILE,
  TEXTAREA_MIN_HEIGHT,
} as const;
