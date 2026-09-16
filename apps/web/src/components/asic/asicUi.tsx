// Re-export shim — the primitives moved to the shared kit (src/ui/kit.tsx) so
// every tab can use them; the ASIC module's imports keep working unchanged.
export {
  card,
  th,
  td,
  Chip,
  ConfidenceBadge,
  GateDot,
  Kpi,
  SectionCard,
  btn,
  LiveChip,
} from "../../ui/kit";
