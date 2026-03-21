// frontend/src/utils/deterministicRandom.ts
// ADDED: Deterministic position generator for reproducible node placement

/**
 * # Deterministic Hash Function for Node Positions
 * 
 * Uses a simple string hash (djb2 variant) to generate reproducible
 * pseudo-random positions from node_id and seed.
 * 
 * Properties:
 * - Same (node_id, seed) → same position (deterministic)
 * - Different node_id → different positions (low collision)
 * - Positions uniformly distributed in [0, 1) range
 * 
 * Time Complexity: O(n) where n = node_id.length
 * Space Complexity: O(1)
 */

/**
 * Simple string hash function (djb2 variant)
 * @param str - Input string to hash
 * @returns 32-bit integer hash
 */
function hashString(str: string): number {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) + str.charCodeAt(i);
    hash = hash >>> 0; // Convert to unsigned 32-bit
  }
  return hash;
}

/**
 * Generate deterministic pseudo-random number in [0, 1)
 * @param seed - Integer seed value
 * @returns Float in [0, 1)
 */
function deterministicRandom(seed: number): number {
  // Linear congruential generator (LCG) parameters
  const a = 1664525;
  const c = 1013904223;
  const m = Math.pow(2, 32);
  
  const next = (a * seed + c) % m;
  return next / m;
}

/**
 * Generate deterministic position for a node
 * @param nodeId - Unique identifier for the node
 * @param seed - Optional seed for variation (default: 0)
 * @param viewportWidth - Width of viewport for positioning (default: 1000)
 * @param viewportHeight - Height of viewport for positioning (default: 1000)
 * @returns { x: number, y: number } position in viewport coordinates
 */
export function hashPosition(
  nodeId: string,
  seed: number = 0,
  viewportWidth: number = 1000,
  viewportHeight: number = 1000
): { x: number; y: number } {
  // Combine nodeId and seed for unique hash
  const combined = `${nodeId}:${seed}`;
  const baseHash = hashString(combined);
  
  // Generate two independent pseudo-random values for x and y
  const hashX = deterministicRandom(baseHash);
  const hashY = deterministicRandom(baseHash ^ 0x9e3779b9); // XOR with golden ratio
  
  // Map to viewport coordinates with padding
  const padding = 50;
  const usableWidth = viewportWidth - padding * 2;
  const usableHeight = viewportHeight - padding * 2;
  
  return {
    x: padding + hashX * usableWidth,
    y: padding + hashY * usableHeight,
  };
}

/**
 * Generate offset for avoiding collisions with existing nodes
 * @param basePosition - Base deterministic position
 * @param existingPositions - Array of existing node positions
 * @param minDistance - Minimum distance between nodes
 * @returns Adjusted position with offset if needed
 */
export function avoidCollisions(
  basePosition: { x: number; y: number },
  existingPositions: Array<{ x: number; y: number }>,
  minDistance: number = 150
): { x: number; y: number } {
  let position = { ...basePosition };
  let offset = 0;
  const maxAttempts = 10;
  
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    let collision = false;
    
    for (const existing of existingPositions) {
      const dx = position.x - existing.x;
      const dy = position.y - existing.y;
      const distance = Math.sqrt(dx * dx + dy * dy);
      
      if (distance < minDistance) {
        collision = true;
        break;
      }
    }
    
    if (!collision) {
      return position;
    }
    
    // Apply spiral offset for next attempt
    offset += 1;
    const angle = offset * 0.61803398875; // Golden angle
    position = {
      x: basePosition.x + Math.cos(angle) * offset * 20,
      y: basePosition.y + Math.sin(angle) * offset * 20,
    };
  }
  
  // Return last attempt even if collision remains
  return position;
}
