#!/usr/bin/env python3
"""Fetch stored match report(s) for a session and send to job portal using
`app.services.job_portal_client.update_application_match`.

Usage: run from repository root:
    python3 scripts/send_report_for_session.py

The session id to send is set in the SESSION_ID constant below.
"""
import asyncio
import logging
from dotenv import load_dotenv

from app.services.db import AsyncSessionLocal
from app.models.new_models import NewReport
from sqlalchemy import select
from app.services import job_portal_client

load_dotenv()

SESSION_ID = "621772c0-ff1e-47be-9c14-9f4c6ae8cfc8"

logging.basicConfig(level=logging.INFO)


async def main():
    async with AsyncSessionLocal() as db:
        stmt = select(NewReport).where(NewReport.session_id == SESSION_ID)
        res = await db.execute(stmt)
        reports = res.scalars().all()

        if not reports:
            print(f"No reports found for session {SESSION_ID}")
            return

        job_id = reports[0].jd_id
        processed_results = []

        for r in reports:
            pr = {
                "cv_id": r.cv_id,
                "total_score": float(r.total_score) if r.total_score is not None else 0.0,
                "category": r.category or "",
                "rationale": r.rationale or "",
            }

            if r.sim_embed is not None:
                try:
                    pr["sim_embed"] = float(r.sim_embed)
                except Exception:
                    pr["sim_embed"] = r.sim_embed

            if r.skill_coverage is not None:
                try:
                    pr["skill_coverage"] = float(r.skill_coverage)
                except Exception:
                    pr["skill_coverage"] = r.skill_coverage

            if r.must_have_penalty is not None:
                pr["must_have_penalty"] = float(r.must_have_penalty)

            if r.llm_consistency is not None:
                pr["llm_consistency"] = float(r.llm_consistency)

            processed_results.append(pr)

        print(f"Sending {len(processed_results)} result(s) for job {job_id} to job portal ({len(processed_results)} CVs)")

        # Call update_application_match from job_portal_client
        response = job_portal_client.update_application_match(processed_results)
        print("Job portal response:")
        print(response)


if __name__ == "__main__":
    asyncio.run(main())
