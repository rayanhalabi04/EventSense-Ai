"""Reliable, rerunnable demo seed for EventSense AI (Phase 1, Step 1).

This builds a *populated* demo environment entirely through the real backend
services — no fake/shortcut data — so every dashboard page has meaningful,
tenant-isolated content:

- two tenants (Elegant Weddings, Royal Events) with a manager **and** a staff
  user each;
- tenant-specific RAG documents with intentionally *different* policies, created
  through :class:`DocumentService` (real chunking + embedding + audit);
- realistic inbound conversations covering pricing/booking/urgent/guest-count/
  complaint/payment/cancellation plus one unsupported question, created through
  :class:`SimulatorService` (real intent classification + risk detection +
  guardrail + audit, same path the WhatsApp simulator uses);
- grounded suggested replies and an unsupported-source refusal, via
  :func:`generate_suggested_reply` (staff-review drafts only — nothing is sent);
- focused-agent analysis + applied recommendations, via
  :class:`AgentOrchestratorService`, which populate the Tasks and Escalations
  pages and the audit log.

Safety / correctness:
- It layers on top of :func:`app.seed.seed_demo_data` and never deletes data.
- It is **safe to rerun**: documents are skipped by title and whole scenarios are
  skipped when their conversation already exists, so a second run is a no-op.
- Tenant isolation is preserved — each tenant is seeded under its own
  :class:`TenantContext`, and every service call scopes writes to that tenant.
- No client message is ever auto-sent: suggested replies stay ``draft`` and the
  agent only *recommends*/creates tasks and escalations.

Two seed modes are available:

- ``docs`` (``make seed-demo-docs``) — tenants/users + tenant documents only
  (chunked/embedded through :class:`DocumentService`). Nothing conversational is
  created. This is the setup for a *live* Telegram/WhatsApp demo where the
  inbound traffic is real.
- ``full`` (``make seed-demo`` / ``make seed-demo-full``) — everything ``docs``
  builds, plus simulator conversations/messages, suggested replies, and
  agent-created tasks/escalations for a self-contained offline demo.

Tenant document *content* is no longer hardcoded: each document is read from a
sample file under ``data/tenant-documents/<tenant-slug>/`` — the same kind of
file a real agency would upload through the Documents page.

Run it (against the running Docker stack) with::

    make seed-demo-docs   # documents only
    make seed-demo-full   # full populated demo (alias: make seed-demo)
    # or directly inside the api container:
    docker compose exec api python -m app.seed_demo --mode docs
    docker compose exec api python -m app.seed_demo --mode full
"""
import argparse
import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.core.tenant_context import TenantContext
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.document import DocumentCreate
from app.seed import seed_demo_data
from app.services.agent_orchestrator_service import AgentOrchestratorService
from app.services.conversation_memory_service import ConversationMemoryService
from app.services.document_service import DocumentService
from app.services.simulator_service import SimulatorService
from app.services.suggested_reply_service import generate_suggested_reply


# Additional staff logins (managers are created by app.seed.seed_demo_data).
# Documented in the README alongside the manager credentials.
DEMO_STAFF = [
    {
        "slug": "elegant-weddings",
        "email": "staff@elegant-weddings.demo",
        "password": "demo-staff-1",
        "full_name": "Elegant Weddings Staff",
    },
    {
        "slug": "royal-events-agency",
        "email": "staff@royal-events.demo",
        "password": "demo-staff-2",
        "full_name": "Royal Events Staff",
    },
]


class SeedMode(str, Enum):
    """Which slice of the demo to build."""

    # tenants/users + tenant documents only (real Telegram/WhatsApp demo setup).
    docs = "docs"
    # docs + simulator conversations, replies, agent tasks/escalations.
    full = "full"


@dataclass(frozen=True)
class DemoDocument:
    """A tenant document whose *content* lives in a sample file on disk.

    ``filename`` is resolved under ``data/tenant-documents/<tenant-slug>/`` — the
    title and type are the metadata an agency would pick when uploading it.
    """

    filename: str
    title: str
    document_type: DocumentType


@dataclass(frozen=True)
class DemoScenario:
    key: str
    client_name: str
    client_contact: str
    body: str
    # Generate a staff-review suggested reply (grounded or refusal) for this one.
    generate_reply: bool = False
    # Run the focused agent and apply its recommendation (idempotent server-side).
    run_agent: bool = False


# --- Tenant document packs (intentionally different policies per tenant) -------
# Content is read from sample files under data/tenant-documents/<slug>/ so the
# seed mirrors a real agency uploading its own documents. The title/type below
# are the metadata a manager would choose on the Documents page; the two tenants
# keep deliberately different pricing/cancellation/deposit policies so
# tenant-scoped RAG and isolation are visible in the demo.

ELEGANT_DOCS = [
    DemoDocument("pricing-packages.txt", "Elegant Weddings Pricing & Packages", DocumentType.package),
    DemoDocument("cancellation-policy.txt", "Elegant Weddings Cancellation Policy", DocumentType.cancellation_policy),
    DemoDocument("deposit-policy.txt", "Elegant Weddings Deposit Policy", DocumentType.deposit_policy),
    DemoDocument("faq.txt", "Elegant Weddings FAQ", DocumentType.faq),
]

ROYAL_DOCS = [
    DemoDocument("pricing-packages.txt", "Royal Events Pricing & Packages", DocumentType.package),
    DemoDocument("cancellation-policy.txt", "Royal Events Cancellation Policy", DocumentType.cancellation_policy),
    DemoDocument("deposit-policy.txt", "Royal Events Deposit Policy", DocumentType.deposit_policy),
    DemoDocument("faq.txt", "Royal Events FAQ", DocumentType.faq),
]

DOCS_BY_SLUG = {
    "elegant-weddings": ELEGANT_DOCS,
    "royal-events-agency": ROYAL_DOCS,
}


def _tenant_documents_root() -> Path:
    """Locate ``data/tenant-documents/`` on the host *and* in the api container.

    Override with ``TENANT_DOCUMENTS_DIR`` if the layout differs. Defaults try
    the repo checkout (run from the host) and ``/app/data/tenant-documents``
    (the directory docker-compose mounts into the api container).
    """
    override = os.getenv("TENANT_DOCUMENTS_DIR")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / "data" / "tenant-documents",  # repo checkout (host)
        Path("/app/data/tenant-documents"),             # mounted in api container
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def _read_document_text(slug: str, doc: DemoDocument) -> str:
    path = _tenant_documents_root() / slug / doc.filename
    if not path.is_file():
        raise FileNotFoundError(
            f"sample document not found: {path}. Expected a file under "
            "data/tenant-documents/ (set TENANT_DOCUMENTS_DIR to override the "
            "location, e.g. when the directory is not mounted into the container)."
        )
    return path.read_text(encoding="utf-8").strip()


# --- Conversation scenarios (shared shape, per-tenant client identities) -------
# Each scenario maps to one of the classifier intents the inbox should showcase.
# The unsupported question uses vocabulary absent from every document so RAG
# reliably refuses (answer_supported=false).

SCENARIOS = [
    DemoScenario(
        key="pricing",
        client_name="Sara Khoury",
        client_contact="+9613001001",
        body="Hi! What are your pricing packages for a 150-guest wedding in June?",
        generate_reply=True,
    ),
    DemoScenario(
        key="booking",
        client_name="Omar Haddad",
        client_contact="+9613001002",
        body="We would love to book your venue for our reception. How do we reserve a date?",
    ),
    DemoScenario(
        key="urgent",
        client_name="Lina Aziz",
        client_contact="+9613001003",
        body="URGENT: we need to change the event start time to tomorrow morning, please help ASAP.",
        run_agent=True,
    ),
    DemoScenario(
        key="guest_count",
        client_name="Rami Saad",
        client_contact="+9613001004",
        body="We need to increase the guest count from 100 to 160 guests for our wedding.",
        run_agent=True,
    ),
    DemoScenario(
        key="complaint",
        client_name="Maya Fares",
        client_contact="+9613001005",
        body="We are very disappointed and unhappy with the service we received. This is unacceptable.",
        run_agent=True,
    ),
    DemoScenario(
        key="payment",
        client_name="Nadia Rizk",
        client_contact="+9613001006",
        body="Our deposit payment was charged twice and the refund has not been received yet.",
        run_agent=True,
    ),
    DemoScenario(
        key="cancellation",
        client_name="Karim Daher",
        client_contact="+9613001007",
        body="We need to cancel our booking. Is the deposit refundable and what refund do we get?",
        generate_reply=True,
        run_agent=True,
    ),
    DemoScenario(
        key="unsupported",
        client_name="Tala Nassar",
        client_contact="+9613001008",
        body="Can you arrange scuba diving lessons and a private yacht for our honeymoon getaway?",
        generate_reply=True,
    ),
]


@dataclass
class Summary:
    mode: str = SeedMode.full.value
    documents_created: int = 0
    documents_skipped: int = 0
    scenarios_created: int = 0
    scenarios_skipped: int = 0
    suggested_replies: int = 0
    refusals: int = 0
    agent_runs: int = 0
    tasks_created: int = 0
    escalations_created: int = 0
    notes: list[str] = field(default_factory=list)


async def _ensure_staff_users(session: AsyncSession) -> None:
    """Add a staff user per tenant (managers come from app.seed). Idempotent."""
    for item in DEMO_STAFF:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == item["slug"]))
        ).scalar_one_or_none()
        if tenant is None:
            continue
        existing = (
            await session.execute(
                select(User).where(User.tenant_id == tenant.id, User.email == item["email"])
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                User(
                    tenant_id=tenant.id,
                    email=item["email"],
                    hashed_password=hash_password(item["password"]),
                    role=UserRole.staff,
                    full_name=item["full_name"],
                )
            )
    await session.commit()


async def _manager_context(session: AsyncSession, tenant: Tenant) -> TenantContext:
    """Build the tenant-scoped context used to drive the real services."""
    manager = (
        await session.execute(
            select(User)
            .where(User.tenant_id == tenant.id, User.role == UserRole.manager)
            .order_by(User.created_at.asc())
            .limit(1)
        )
    ).scalar_one()
    return TenantContext(user_id=manager.id, tenant_id=tenant.id, role=UserRole.manager)


async def _seed_documents(
    session: AsyncSession, ctx: TenantContext, slug: str, summary: Summary
) -> None:
    existing_titles = set(
        (
            await session.execute(
                select(Document.title).where(Document.tenant_id == ctx.tenant_id)
            )
        )
        .scalars()
        .all()
    )
    service = DocumentService(session)
    for doc in DOCS_BY_SLUG.get(slug, []):
        if doc.title in existing_titles:
            summary.documents_skipped += 1
            continue
        content_text = _read_document_text(slug, doc)
        await service.create_document(
            DocumentCreate(
                title=doc.title,
                document_type=doc.document_type,
                original_filename=doc.filename,
                content_text=content_text,
                status=DocumentStatus.active,
            ),
            ctx,
        )
        summary.documents_created += 1


async def _seed_scenario(
    session: AsyncSession,
    ctx: TenantContext,
    tenant: Tenant,
    scenario: DemoScenario,
    summary: Summary,
) -> None:
    conversations = ConversationRepository(session)
    existing = await conversations.find_latest_by_client(
        ctx.tenant_id,
        client_name=scenario.client_name,
        client_contact=scenario.client_contact,
    )
    if existing is not None:
        # Already seeded on a previous run — skip the whole scenario so reruns
        # never pile up duplicate messages/replies/tasks.
        summary.scenarios_skipped += 1
        return

    conversation, _, _ = await SimulatorService.resolve_or_create_conversation(
        session=session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        client_name=scenario.client_name,
        client_contact=scenario.client_contact,
        conversation_id=None,
    )
    message = await SimulatorService.create_inbound_message(
        session=session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        conversation=conversation,
        body=scenario.body,
    )
    await session.commit()
    summary.scenarios_created += 1

    # Mirror the simulator endpoint: copy inbound into short-term memory (no-op
    # when MEMORY_ENABLED is false / Redis is unavailable).
    await ConversationMemoryService().store_inbound_message(
        tenant_id=ctx.tenant_id, message=message
    )

    if scenario.generate_reply:
        reply = await generate_suggested_reply(
            session,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            conversation=conversation,
            message=message,
        )
        if reply.answer_supported:
            summary.suggested_replies += 1
        else:
            summary.refusals += 1

    if scenario.run_agent:
        orchestrator = AgentOrchestratorService(session)
        decision = orchestrator.run(message=message, ctx=ctx)
        summary.agent_runs += 1
        if decision.ran:
            applied = await orchestrator.apply_decision(
                decision=decision,
                conversation_id=conversation.id,
                message=message,
                ctx=ctx,
            )
            if applied.task_id is not None:
                summary.tasks_created += 1
            if applied.escalation_id is not None:
                summary.escalations_created += 1
        await session.commit()


async def seed_demo(mode: SeedMode = SeedMode.full) -> Summary:
    # Base tenants + manager users (reuses the existing seed; safe to rerun).
    await seed_demo_data()

    summary = Summary(mode=mode.value)
    async with AsyncSessionLocal() as session:
        await _ensure_staff_users(session)

        for slug in DOCS_BY_SLUG:
            tenant = (
                await session.execute(select(Tenant).where(Tenant.slug == slug))
            ).scalar_one_or_none()
            if tenant is None:
                summary.notes.append(f"tenant '{slug}' not found — skipped")
                continue

            ctx = await _manager_context(session, tenant)
            await _seed_documents(session, ctx, slug, summary)
            # docs mode stops at documents — no conversations/replies/tasks so
            # the inbox is empty and ready for real Telegram/WhatsApp traffic.
            if mode is SeedMode.full:
                for scenario in SCENARIOS:
                    await _seed_scenario(session, ctx, tenant, scenario, summary)

    return summary


def _print_summary(summary: Summary) -> None:
    print(f"\nEventSense AI demo seed complete (mode={summary.mode}).")
    print(f"  documents:    created={summary.documents_created} skipped={summary.documents_skipped}")
    if summary.mode == SeedMode.full.value:
        print(f"  scenarios:    created={summary.scenarios_created} skipped={summary.scenarios_skipped}")
        print(f"  replies:      grounded={summary.suggested_replies} refusals={summary.refusals}")
        print(f"  agent runs:   {summary.agent_runs}")
        print(f"  tasks:        created={summary.tasks_created}")
        print(f"  escalations:  created={summary.escalations_created}")
    else:
        print("  scenarios:    skipped (docs mode — inbox left empty for live demo)")
    for note in summary.notes:
        print(f"  note: {note}")
    print("\nDemo logins:")
    print("  Elegant Weddings  manager  admin@elegant-weddings.demo / demo-password-1")
    print("  Elegant Weddings  staff    staff@elegant-weddings.demo / demo-staff-1")
    print("  Royal Events      manager  admin@royal-events.demo / demo-password-2")
    print("  Royal Events      staff    staff@royal-events.demo / demo-staff-2")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the EventSense AI demo environment.")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in SeedMode],
        default=SeedMode.full.value,
        help=(
            "'docs' seeds tenants/users + tenant documents only (live "
            "Telegram/WhatsApp demo setup); 'full' (default) also seeds "
            "conversations, replies, and agent tasks/escalations."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = asyncio.run(seed_demo(SeedMode(args.mode)))
    _print_summary(result)
