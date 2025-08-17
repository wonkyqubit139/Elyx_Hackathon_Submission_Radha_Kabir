import json, random, uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SGT = timezone(timedelta(hours=8))

# ------------ Data Models ------------

@dataclass
class Message:
    id: str
    ts: str
    day: str
    sender_id: str
    sender_name: str
    sender_role: str
    to: str
    text: str
    tags: list
    related_decision_ids: list

@dataclass
class Decision:
    id: str
    ts: str
    actor_id: str
    actor_name: str
    actor_role: str
    kind: str           # "plan_update" | "medication" | "therapy" | "test" | "protocol"
    title: str
    rationale: str
    triggers: dict      # {"message_ids":[], "test_ids":[], "metrics":[]}
    effects: dict       # {"plan_changes":[], "followups":[]}

@dataclass
class Test:
    id: str
    ts: str
    panel: str          # "Quarterly Panel" / "DEXA" / "VO2" etc.
    summary: str
    highlights: dict    # {"ApoB": 105, "hsCRP": 1.2, ...}

# ------------ Utilities ------------

def iso(dt): return dt.astimezone(SGT).isoformat()

ROLES = {
    "U-RUBY": ("Ruby", "Concierge"),
    "U-NEEL": ("Neel", "Concierge Lead"),
    "U-WARREN": ("Dr. Warren", "Medical"),
    "U-RACHEL": ("Rachel", "PT"),
    "U-CARLA": ("Carla", "Nutrition"),
    "U-ADVIK": ("Advik", "Lifestyle"),
    "M-001": ("Rohan", "Member")
}

def new_id(prefix): return f"{prefix}-{uuid.uuid4().hex[:8]}"

# ------------ Simulator ------------

class ElyxSimulator:
    def __init__(self, cfg):
        self.cfg = cfg
        self.start = datetime.fromisoformat(cfg["simulation"]["start_date"]).replace(tzinfo=SGT)
        self.months = cfg["simulation"]["months"]
        self.end = self.start + timedelta(days=30*self.months)
        self.rng = random.Random(cfg["simulation"]["seed"])
        self.messages, self.decisions, self.tests = [], [], []
        self.internal_hours = {r: 0.0 for r in ["Medical","PT","Nutrition","Lifestyle","Concierge","Concierge Lead"]}
        self.last_exercise_update = self.start
        self.travel_weeks = set()

    def run(self):
        current = self.start
        week_idx = 0
        diagnostic_months = set(self.cfg["simulation"]["diagnostic_panel_months"])
        adherence_p = self.cfg["simulation"]["adherence_probability"]
        max_member_threads = self.cfg["simulation"]["max_member_threads_per_week"]

        # Pre-choose travel weeks (every 4 weeks)
        while current < self.end:
            if week_idx % self.cfg["simulation"]["travel_week_every_n_weeks"] == 3:
                self.travel_weeks.add(current.isocalendar()[:2])  # (year, week)
            current += timedelta(days=7)
            week_idx += 1

        current = self.start
        while current < self.end:
            y, w, _ = current.isocalendar()
            is_travel = (y, w) in self.travel_weeks
            day_str = current.strftime("%Y-%m-%d")

            # Member-initiated threads (cap per week)
            threads_today = 0
            if current.weekday() < 5:  # weekdays likelier
                weekly_threads = self._weekly_member_threads(y, w, max_member_threads)
                remaining_today = max(0, weekly_threads - self._count_week_member_threads(y, w))
                threads_today = self.rng.randint(0, min(2, remaining_today))

            for _ in range(threads_today):
                self._member_reaches_out(current, day_str, is_travel)

            # Routine scheduled touches (concierge check-in, PT/Nutrition)
            if current.weekday() in (0, 3):  # concierge twice weekly
                self._concierge_checkin(current, day_str, is_travel)

            # Exercise update every 14 days
            if (current - self.last_exercise_update).days >= self.cfg["simulation"]["exercise_update_days"]:
                self._exercise_update(current, day_str, adherence_p, is_travel)

            # Monthly diagnostics (every 3 months relative to start)
            month_num = (current.year - self.start.year)*12 + (current.month - self.start.month) + 1
            if current.day == 10 and month_num in diagnostic_months:
                self._quarterly_panel(current, day_str)

            current += timedelta(days=1)

    # ---- Helpers ----

    def _count_week_member_threads(self, year, week):
        return sum(1 for m in self.messages
                   if m.sender_role=="Member" and datetime.fromisoformat(m.ts).isocalendar()[:2]==(year,week))

    def _weekly_member_threads(self, year, week, cap):
        # draw once per week a target number up to cap
        self.rng.seed(f"wk-{year}-{week}-{self.cfg['simulation']['seed']}")
        return self.rng.randint(2, cap)

    def _emit_message(self, dt, sender_id, to, text, tags=None, rel=None):
        name, role = ROLES[sender_id]
        mid = new_id("MSG")
        msg = Message(
            id=mid, ts=iso(dt), day=dt.strftime("%Y-%m-%d"),
            sender_id=sender_id, sender_name=name, sender_role=role,
            to=to, text=text, tags=tags or [], related_decision_ids=rel or []
        )
        self.messages.append(msg)
        # crude internal-hours accounting
        if role in self.internal_hours and role != "Member":
            self.internal_hours[role] += 0.1  # 6 minutes per message touch
        return msg

    def _emit_decision(self, dt, actor_id, kind, title, rationale, triggers, effects):
        name, role = ROLES[actor_id]
        did = new_id("DEC")
        dec = Decision(
            id=did, ts=iso(dt),
            actor_id=actor_id, actor_name=name, actor_role=role,
            kind=kind, title=title, rationale=rationale,
            triggers=triggers, effects=effects
        )
        self.decisions.append(dec)
        if role in self.internal_hours:
            self.internal_hours[role] += 0.5  # 30 min per decision
        return dec

    # ---- Event logic ----

    def _member_reaches_out(self, dt, day_str, is_travel):
        # Sample topics: sleep issue, ApoB question, workout tweak, travel fatigue, wearable question
        topics = [
            ("sleep", "Rohan: Had poor deep sleep last night. Any quick fixes?"),
            ("apoB", "Rohan: I read about ApoB targets. What’s a realistic goal for me?"),
            ("workout", "Rohan: Can we swap today’s session? Hotel gym is limited."),
            ("travel", "Rohan: Jet lag is rough this trip. How should I adjust today?"),
            ("wearable", "Rohan: Why is my HRV down despite a rest day?")
        ]
        tag, text = self.rng.choice(topics)
        self._emit_message(dt.replace(hour=9), "M-001", "U-RUBY", text, tags=[tag, "member_initiated"])

        # concierge routes to specialist
        route = {
            "sleep":"U-ADVIK", "apoB":"U-WARREN",
            "workout":"U-RACHEL", "travel":"U-ADVIK", "wearable":"U-ADVIK"
        }[tag]
        self._emit_message(dt.replace(hour=9, minute=10), "U-RUBY", route,
                           f"Routing to {ROLES[route][0]} for guidance.", tags=["routing"])

        if route == "U-WARREN" and tag=="apoB":
            # possible medication/plan consideration; we’ll keep it non-prescriptive for hackathon
            dec = self._emit_decision(
                dt.replace(hour=10), "U-WARREN", "plan_update",
                "ApoB reduction strategy",
                "Elevated ApoB + member interest → tighten nutrition & add fiber protocol before pharmacotherapy.",
                triggers={"message_ids": [self.messages[-2].id], "test_ids": [], "metrics":["ApoB: elevated"]},
                effects={"plan_changes":["Increase soluble fiber 10-15g/day", "Olive oil for cooking", "Repeat panel in 90 days"], "followups":["Nutrition check-in weekly"]}
            )
            self._emit_message(dt.replace(hour=10, minute=5), "U-CARLA", "M-001",
                               "I’ll set Javier’s plan: more legumes/oats + psyllium. We’ll monitor bloating & CGM.", tags=["nutrition"],
                               rel=[dec.id])

    def _concierge_checkin(self, dt, day_str, is_travel):
        self._emit_message(dt.replace(hour=11), "U-RUBY", "M-001",
                           "Weekly check-in: any blockers to the plan? I can help coordinate.",
                           tags=["checkin","concierge"])

    def _exercise_update(self, dt, day_str, adherence_p, is_travel):
        self.last_exercise_update = dt
        adhered = self.rng.random() < adherence_p and not is_travel
        if adhered:
            title = "Progression: increase Zone 2 by +5 min"
            rationale = "Consistent adherence & stable HR/HRV trends → progressive overload."
        else:
            title = "Adjustment: maintain volume; add travel-safe routine"
            rationale = "Low adherence and/or travel constraints → keep volume steady and add bodyweight set."

        dec = self._emit_decision(
            dt.replace(hour=14), "U-RACHEL", "plan_update", title, rationale,
            triggers={"message_ids": [], "test_ids": [], "metrics":["adherence","travel" if is_travel else "home"]},
            effects={"plan_changes":[title], "followups":["PT check-in in 1 week"]}
        )
        self._emit_message(dt.replace(hour=14, minute=10), "U-RACHEL", "M-001",
                           f"{title}. I’ve pushed it to your app.", tags=["exercise_update"], rel=[dec.id])

    def _quarterly_panel(self, dt, day_str):
        # Emit a lab panel with ApoB + hsCRP + fasting glucose
        apoB = self.rng.randint(90, 115)   # nudge around elevated
        hsCRP = round(self.rng.uniform(0.5, 2.0), 2)
        fpg = self.rng.randint(85, 102)

        test = Test(new_id("TST"), iso(dt.replace(hour=8)), "Quarterly Panel",
                    "Comprehensive biomarkers (ApoB, hsCRP, FPG).",
                    {"ApoB": apoB, "hsCRP": hsCRP, "FPG": fpg})
        self.tests.append(test)

        self._emit_message(dt.replace(hour=8, minute=30), "U-RUBY", "U-WARREN",
                           "Panel results have arrived; routing for analysis.", tags=["labs"])

        # medical decision referencing the panel
        rec = "Nutrition-first + fiber protocol; recheck in 90 days."
        if apoB >= 110:
            rec = "Intensify nutrition + discuss pharmacotherapy candidly; recheck in 90 days."

        dec = self._emit_decision(
            dt.replace(hour=12), "U-WARREN", "test",
            "Quarterly Panel Review",
            f"Panel shows ApoB={apoB}, hsCRP={hsCRP}, FPG={fpg}. {rec}",
            triggers={"message_ids":[self.messages[-1].id], "test_ids":[test.id], "metrics":[f"ApoB:{apoB}"]},
            effects={"plan_changes":[rec], "followups":["Q&A with member","Nutrition plan tweaks"]}
        )

        # notify member
        self._emit_message(dt.replace(hour=12, minute=15), "U-WARREN", "M-001",
                           f"Your panel is back. ApoB={apoB}. I recommend: {rec}",
                           tags=["labs","summary"], rel=[dec.id])

def main():
    cfg = json.loads(Path("data/config_member.json").read_text())
    sim = ElyxSimulator(cfg)
    sim.run()

    outdir = Path("data/generated")
    outdir.mkdir(parents=True, exist_ok=True)

    with (outdir/"messages.jsonl").open("w") as f:
        for m in sim.messages:
            f.write(json.dumps(asdict(m), ensure_ascii=False)+"\n")

    with (outdir/"decisions.jsonl").open("w") as f:
        for d in sim.decisions:
            f.write(json.dumps(asdict(d), ensure_ascii=False)+"\n")

    with (outdir/"tests.jsonl").open("w") as f:
        for t in sim.tests:
            f.write(json.dumps(asdict(t), ensure_ascii=False)+"\n")

    metrics = {
        "internal_hours": sim.internal_hours,
        "message_count": len(sim.messages),
        "decision_count": len(sim.decisions),
        "test_count": len(sim.tests)
    }
    (outdir/"metrics.json").write_text(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    main()

