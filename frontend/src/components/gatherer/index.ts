/**
 * Gatherer Components
 *
 * The page-level Gatherer.tsx composes the lab masthead + section head +
 * footer inline; the body sections (`Lab*`) are exported from here. The
 * card cells (`SketchCard` / `SketchCardDetail`) keep their existing
 * parchment chrome per the per-card-identity rule in
 * `docs/design/brand.md`.
 */

export { SketchCard } from './SketchCard';
export { SketchCardDetail } from './SketchCardDetail';
export { LabSetSidebar } from './LabSetSidebar';
export { LabFilterBar, LabFilterToolbar } from './LabFilterBar';
export { LabCardGrid } from './LabCardGrid';
export { LabPaginationFooter } from './LabPaginationFooter';
export { LabCardDetailModal } from './LabCardDetailModal';
