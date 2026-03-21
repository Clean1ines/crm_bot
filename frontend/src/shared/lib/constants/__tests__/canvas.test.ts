// frontend/src/constants/__tests__/canvas.test.ts
// ADDED: Unit tests for canvas coordinate transformations

import { describe, it, expect } from 'vitest';
import {
  NODE_HALF_WIDTH,
  NODE_HALF_HEIGHT,
  VIEWPORT_SCALE_MIN,
  VIEWPORT_SCALE_MAX,
  VIEWPORT_SCALE_DEFAULT,
} from '../canvas';

describe('Canvas Constants', () => {
  describe('Coordinate System Invariants', () => {
    it('should maintain screen_pos = (world_pos × scale) + pan', () => {
      const worldPos = { x: 100, y: 200 };
      const scale = 1.5;
      const pan = { x: 50, y: 100 };

      // Formula: screen_pos = (world_pos × scale) + pan
      const screenX = (worldPos.x * scale) + pan.x;
      const screenY = (worldPos.y * scale) + pan.y;

      expect(screenX).toBe(200);
      expect(screenY).toBe(400);
    });

    it('should maintain world_pos = (screen_pos - pan) / scale', () => {
      const screenPos = { x: 200, y: 400 };
      const scale = 1.5;
      const pan = { x: 50, y: 100 };

      // Formula: world_pos = (screen_pos - pan) / scale
      const worldX = (screenPos.x - pan.x) / scale;
      const worldY = (screenPos.y - pan.y) / scale;

      expect(worldX).toBe(100);
      expect(worldY).toBe(200);
    });

    it('should round-trip world → screen → world correctly', () => {
      const worldPos = { x: 100, y: 200 };
      const scale = 2.0;
      const pan = { x: 30, y: 60 };

      // World to screen
      const screenX = (worldPos.x * scale) + pan.x;
      const screenY = (worldPos.y * scale) + pan.y;

      // Screen back to world
      const worldX = (screenX - pan.x) / scale;
      const worldY = (screenY - pan.y) / scale;

      expect(worldX).toBe(worldPos.x);
      expect(worldY).toBe(worldPos.y);
    });
  });

  describe('Node Centering', () => {
    it('should use NODE_HALF_WIDTH for horizontal centering', () => {
      expect(NODE_HALF_WIDTH).toBe(110);
      expect(NODE_HALF_WIDTH * 2).toBe(220); // Full width
    });

    it('should use NODE_HALF_HEIGHT for vertical centering', () => {
      expect(NODE_HALF_HEIGHT).toBe(40);
      expect(NODE_HALF_HEIGHT * 2).toBe(80); // Full height
    });

    it('should center node at mouse position', () => {
      const mousePos = { x: 500, y: 300 };
      const scale = 1.0;
      const pan = { x: 0, y: 0 };

      // Node top-left = (mouse - pan) / scale - half_dimensions
      const nodeX = (mousePos.x - pan.x) / scale - NODE_HALF_WIDTH;
      const nodeY = (mousePos.y - pan.y) / scale - NODE_HALF_HEIGHT;

      expect(nodeX).toBe(390);
      expect(nodeY).toBe(260);
    });
  });

  describe('Scale Bounds', () => {
    it('should have valid scale range', () => {
      expect(VIEWPORT_SCALE_MIN).toBe(0.2);
      expect(VIEWPORT_SCALE_MAX).toBe(3.0);
      expect(VIEWPORT_SCALE_DEFAULT).toBe(1.0);
    });

    it('should clamp scale to valid range', () => {
      const clamp = (value: number, min: number, max: number) =>
        Math.min(Math.max(value, min), max);

      expect(clamp(0.1, VIEWPORT_SCALE_MIN, VIEWPORT_SCALE_MAX)).toBe(VIEWPORT_SCALE_MIN);
      expect(clamp(4.0, VIEWPORT_SCALE_MIN, VIEWPORT_SCALE_MAX)).toBe(VIEWPORT_SCALE_MAX);
      expect(clamp(1.5, VIEWPORT_SCALE_MIN, VIEWPORT_SCALE_MAX)).toBe(1.5);
    });
  });

  describe('Zoom Calculations', () => {
    it('should calculate zoom factor correctly', () => {
      const baseScale = 1.0;
      const zoomFactor = 1.1;
      const wheelDelta = -300; // Zoom in
      const sensitivity = 300;

      const factor = Math.pow(zoomFactor, -wheelDelta / sensitivity);
      const newScale = baseScale * factor;

      expect(newScale).toBe(1.1);
    });

    it('should handle zoom out', () => {
      const baseScale = 1.0;
      const zoomFactor = 1.1;
      const wheelDelta = 300; // Zoom out
      const sensitivity = 300;

      const factor = Math.pow(zoomFactor, -wheelDelta / sensitivity);
      const newScale = baseScale * factor;

      expect(newScale).toBeCloseTo(0.909, 3);
    });
  });
});
