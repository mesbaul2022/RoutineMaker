"""Configure teacher assignments for batches 3-1 and 4-2 to enable 5-batch simulation testing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal, Batch, Course, Teacher, Assignment

def setup():
    with SessionLocal() as db:
        assign_31 = {
            "CSE3100": ("al_mahmud", "ehsanul_karim"),
            "CSE3101": ("sk_md_masudul_ahsan", "kazi_md_rokibul_alam"),
            "CSE3102": ("sk_md_masudul_ahsan", "kazi_md_rokibul_alam"),
            "CSE3105": ("muhammad_sheikh_sadi", "md_faisal_hossain"),
            "CSE3106": ("muhammad_sheikh_sadi", "md_faisal_hossain"),
            "CSE3107": ("md_milon_islam", "subah_nawar"),
            "CSE3109": ("mma_hashem", "md_faruque_hossain"),
            "CSE3110": ("mma_hashem", "md_faruque_hossain"),
            "CSE3119": ("md_badiuzzaman_shuvo", "sadia_islam"),
            "CSE3120": ("md_badiuzzaman_shuvo", "sadia_islam"),
        }

        for cid, (t1, t2) in assign_31.items():
            c = db.query(Course).filter_by(id=cid).first()
            if c:
                c.teacher1_id = t1
                c.teacher2_id = t2
                db.query(Assignment).filter_by(course_id=cid).delete()
                for s in ["A", "B"]:
                    if c.kind == "theory":
                        db.add(Assignment(course_id=cid, section=s, group=None, teacher_id=t1))
                        db.add(Assignment(course_id=cid, section=s, group=None, teacher_id=t2))
                    else:
                        for g in ["G1", "G2"]:
                            db.add(Assignment(course_id=cid, section=s, group=g, teacher_id=t1))
                            db.add(Assignment(course_id=cid, section=s, group=g, teacher_id=t2))

        offered_42 = {
            "CSE4000": ("sk_md_masudul_ahsan", "al_mahmud"),
            "IEM4227": ("md_mahbubur_rahman", "miir_anjirin_tazrin"),
            "HUM4207": ("farhana_afroj", "sm_rabiul_alam"),
            "CSE4211": ("mma_hashem", "kazi_md_rokibul_alam"),
            "CSE4203": ("md_milon_islam", "subah_nawar"),
            "CSE4204": ("md_milon_islam", "subah_nawar"),
            "CSE4217": ("waliul_islam_sumon", "sadia_islam"),
            "CSE4218": ("waliul_islam_sumon", "sadia_islam"),
        }

        all_42 = db.query(Course).filter_by(batch_id="4-2").all()
        for c in all_42:
            if c.id not in offered_42:
                db.query(Assignment).filter_by(course_id=c.id).delete()
                db.delete(c)
            else:
                t1, t2 = offered_42[c.id]
                c.teacher1_id = t1
                c.teacher2_id = t2
                db.query(Assignment).filter_by(course_id=c.id).delete()
                for s in ["A", "B"]:
                    if c.kind == "theory":
                        db.add(Assignment(course_id=c.id, section=s, group=None, teacher_id=t1))
                        db.add(Assignment(course_id=c.id, section=s, group=None, teacher_id=t2))
                    else:
                        for g in ["G1", "G2"]:
                            db.add(Assignment(course_id=c.id, section=s, group=g, teacher_id=t1))
                            db.add(Assignment(course_id=c.id, section=s, group=g, teacher_id=t2))

        for t in db.query(Teacher).all():
            t.max_periods_per_day = 8

        db.commit()
        print("Setup completed successfully!")

if __name__ == "__main__":
    setup()
