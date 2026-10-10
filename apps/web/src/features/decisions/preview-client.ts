import examples from "./demo-display.json";
import { validateDetails, type ActionStatus, type Decision, type DecisionDetails, type DecisionSource, type OutcomeReview } from "./model";
type Command = { type: "edit_draft"; details: DecisionDetails } | { type: "submit" | "approve" | "reject" | "start" | "complete" | "cancel" } | { type: "update_action"; action_id: string; status: ActionStatus; occurred_at: string | null; evidence_note: string; actual_cost_minor_units: number | null } | { type: "correct_action_report"; action_id: string; occurred_at: string; evidence_note: string; actual_cost_minor_units: number | null };
export function decisionPreviewStore(storage: Pick<Storage, "getItem" | "setItem">) {
  const key = "healthgrid:decision-ui-preview:v1";
  type Store = { version: 1; decisions: Decision[]; reviews: OutcomeReview[] };
  function read(): Store {
    const raw = storage.getItem(key); if (!raw) return { version: 1, decisions: [], reviews: [] };
    try { const data = JSON.parse(raw) as Store; if (data.version !== 1 || !Array.isArray(data.decisions) || !Array.isArray(data.reviews) || data.decisions.some((item) => !item?.source?.example || !Array.isArray(item.actions) || !Array.isArray(item.events))) throw new Error(); return data; }
    catch { throw new Error("Local decision preview data could not be read. Existing data has not been reset."); }
  }
  function write(data: Store) { storage.setItem(key, JSON.stringify(data)); }
  function prerequisite(data: Store, decision: Decision) {
    if (!decision.source.has_transfer_prerequisite) return;
    const previous = data.decisions.find((item) => item.decision_id === decision.prerequisite_decision_id);
    if (!previous || previous.source.source_type !== "allocation" || previous.source.source_run_id !== decision.source.allocation_run_id || previous.status !== "completed") throw new Error("The exact source allocation decision must be reported completed before investment work starts.");
  }
  function execution(at: string | null, evidence: string, cost: number | null) {
    if (!at || !at.endsWith("Z") || !Number.isFinite(Date.parse(at)) || Date.parse(at) > Date.now()) throw new Error("Supply a valid reported execution timestamp in UTC, not in the future.");
    if (!evidence.trim()) throw new Error("Supply an execution evidence note.");
    if (cost !== null && (!Number.isSafeInteger(cost) || cost < 0)) throw new Error("Actual cost is optional, or a nonnegative whole USD-cent amount. Unknown is not zero.");
  }
  return {
    list: read,
    create(source: DecisionSource, details: DecisionDetails, actor: string) {
      if (!source.example) throw new Error("Server decision contracts are pending. API proposals cannot be saved to the browser preview.");
      const errors = validateDetails(details, actor); if (errors.length) throw new Error(errors.join(" "));
      const data = read();
      if (data.decisions.some((item) => item.source.source_type === source.source_type && item.source.source_run_id === source.source_run_id && !["rejected", "cancelled"].includes(item.status))) throw new Error("This example source already has an active or completed decision. Reopen it instead of tracking duplicate execution.");
      if (source.has_transfer_prerequisite) {
        const previous = data.decisions.find((item) => item.decision_id === details.prerequisite_decision_id);
        if (!previous || previous.source.source_type !== "allocation" || previous.source.source_run_id !== source.allocation_run_id) throw new Error("Select the exact allocation prerequisite decision first. Record the transfer decision before creating the investment decision.");
      }
      if (details.supersedes_decision_id && !data.decisions.some((item) => item.decision_id === details.supersedes_decision_id && ["rejected", "cancelled", "completed"].includes(item.status))) throw new Error("Superseded decision must be an existing terminal record.");
      const recorded_at = new Date().toISOString();
      const decision: Decision = { ...structuredClone(details), decision_id: crypto.randomUUID(), source: structuredClone(source), status: "draft", version: 1, created_at: recorded_at, identity_mode: "demo_self_reported", actions: source.actions.map((item) => ({ ...item, status: "pending", note: "", occurred_at: null, actual_cost_minor_units: null, corrections: [] })), events: [{ event_id: crypto.randomUUID(), type: "created", actor: actor.trim(), note: details.rationale, recorded_at, occurred_at: null, payload: structuredClone(details) }] };
      data.decisions.unshift(decision); write(data); return structuredClone(decision);
    },
    event(id: string, expectedVersion: number, actor: string, note: string, command: Command) {
      if (!actor.trim()) throw new Error("Supply a self-reported demo actor name.");
      const data = read(); const decision = data.decisions.find((item) => item.decision_id === id);
      if (!decision || decision.version !== expectedVersion) throw new Error("This decision changed or is missing. Refresh the board and reopen it before recording another event.");
      const recorded_at = new Date().toISOString();
      const transition = (from: string[], to: Decision["status"]) => { if (!from.includes(decision.status)) throw new Error("This transition is not available from the current decision state."); decision.status = to; };
      if (["approve", "reject", "cancel", "complete", "correct_action_report"].includes(command.type) && !note.trim()) throw new Error("This command requires an explanation/completion note.");
      let occurred_at: string | null = null;
      switch (command.type) {
        case "edit_draft": {
          if (decision.status !== "draft") throw new Error("Only draft details can be edited.");
          const errors = validateDetails(command.details, actor); if (errors.length) throw new Error(errors.join(" "));
          if (command.details.prerequisite_decision_id !== decision.prerequisite_decision_id || command.details.supersedes_decision_id !== decision.supersedes_decision_id) throw new Error("Changing source references requires a new preview decision.");
          Object.assign(decision, structuredClone(command.details)); break;
        }
        case "submit": transition(["draft"], "pending_review"); break;
        case "approve": transition(["pending_review"], "approved"); break;
        case "reject": transition(["pending_review"], "rejected"); break;
        case "start": prerequisite(data, decision); transition(["approved"], "in_progress"); break;
        case "complete":
          if (decision.actions.some((item) => item.status !== "completed")) throw new Error("Every required action must be reported completed first.");
          prerequisite(data, decision); transition(["approved", "in_progress"], "completed"); break;
        case "cancel":
          transition(["draft", "pending_review", "approved", "in_progress"], "cancelled");
          decision.actions = decision.actions.map((item) => item.status === "completed" ? item : { ...item, status: "cancelled" }); break;
        case "update_action": {
          if (!["approved", "in_progress"].includes(decision.status)) throw new Error("Actions cannot start before approval or after the decision becomes terminal.");
          const action = decision.actions.find((item) => item.action_id === command.action_id);
          if (!action || ["completed", "cancelled"].includes(action.status)) throw new Error("Terminal action reports cannot be overwritten. Append a correction with a reason.");
          if (!command.evidence_note.trim()) throw new Error("Supply progress evidence or a blocker note.");
          if (command.status === "in_progress" || command.status === "completed") {
            prerequisite(data, decision);
            if (action.requires_action_ids.some((required) => !decision.actions.some((item) => item.action_id === required && item.status === "completed"))) throw new Error("Report prerequisite actions completed before dependent work starts.");
          }
          if (command.status === "completed") execution(command.occurred_at, command.evidence_note, command.actual_cost_minor_units);
          if (!["in_progress", "blocked", "completed"].includes(command.status)) throw new Error("Use start, blocked or completed for a progress report; cancellation uses decision controls.");
          action.status = command.status; action.note = command.evidence_note; action.occurred_at = command.status === "completed" ? command.occurred_at : null; action.actual_cost_minor_units = command.status === "completed" ? command.actual_cost_minor_units : null;
          occurred_at = action.occurred_at; decision.status = "in_progress"; break;
        }
        case "correct_action_report": {
          const action = decision.actions.find((item) => item.action_id === command.action_id);
          if (!action || action.status !== "completed") throw new Error("Only completed execution reports have correction previews.");
          execution(command.occurred_at, command.evidence_note, command.actual_cost_minor_units);
          action.corrections.push({ actor: actor.trim(), reason: note, occurred_at: command.occurred_at, evidence_note: command.evidence_note, actual_cost_minor_units: command.actual_cost_minor_units, recorded_at }); occurred_at = command.occurred_at; break;
        }
      }
      decision.version += 1; decision.events.push({ event_id: crypto.randomUUID(), type: command.type, actor: actor.trim(), note, recorded_at, occurred_at, payload: structuredClone(command) }); write(data); return structuredClone(decision);
    },
    review(id: string, sample: "insufficient" | "supported" | "below" | "early", actor: string, note: string) {
      if (!actor.trim() || !note.trim()) throw new Error("Supply a reviewer name and evidence-review note.");
      const data = read(); const decision = data.decisions.find((item) => item.decision_id === id); if (!decision) throw new Error("Decision not found.");
      // Explicit frozen display samples. No live report capture or outcome computation.
      const fixture = structuredClone(examples.reviews[decision.source.source_type][sample]);
      const review: OutcomeReview = { ...fixture, review_id: crypto.randomUUID(), decision_id: id, actor: actor.trim(), note, decision_status: decision.status, decision_version: decision.version, example: true } as OutcomeReview;
      data.reviews.unshift(review); write(data); return structuredClone(review);
    },
  };
}
export type PreviewStore = ReturnType<typeof decisionPreviewStore>;
