# scripts/qf_sync.py
import argparse
import os
import sys
import time
from datetime import datetime

import requests
from junitparser import JUnitXml

BASE_URL = "https://xxxxxxxx"


def create_test_cycle(api_key, test_phase_id, test_suite_assignment_id, target_priorities):
    """
    Tạo 1 Test Cycle mới trong QF.
    """
    url = (
        f"{BASE_URL}/test_phases/{test_phase_id}"
        f"/test_suite_assignments/{test_suite_assignment_id}"
        f"/test_cycles.json"
    )

    params = {"api_key": api_key}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    today = datetime.utcnow().strftime("%Y-%m-%d")
    name = f"GitHub AutoTest {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"

    # Nếu bạn chỉ dùng 1 priority (ví dụ "A")
    # có thể truyền qua env QF_TARGET_PRIORITIES="A"
    priorities = [p.strip() for p in str(target_priorities).split(",") if p.strip()]

    # body cơ bản
    data = {
        "test_cycle[name]": name,
        "test_cycle[start_on]": today,
        "test_cycle[end_on]": today,
        # status là SỐ, ví dụ 1 = 未実施 (unexecuted)
        "test_cycle[status]": 1,
        # optional: gửi thêm assignment id, dù đã có trong path
        "test_cycle[test_suite_assignment_id]": test_suite_assignment_id,
    }

    # field bắt buộc: test_cycle[target_priorities][]
    # chỉ cần 1 giá trị A → gửi 1 key thôi là đủ
    # nếu sau này có nhiều priority, có thể gửi nhiều lần key này
    if priorities:
        # requests sẽ encode list(tuple) đúng dạng x-www-form-urlencoded
        payload = list(data.items())
        for p in priorities:
            payload.append(("test_cycle[target_priorities][]", p))
    else:
        payload = list(data.items())

    resp = requests.post(url, params=params, headers=headers, data=payload)

    if not resp.ok:
        print("[QF] Failed to create test cycle:", resp.status_code, resp.text)
        resp.raise_for_status()

    body = resp.json()
    return body["id"]



def parse_junit_results(junit_path):
    """
    Đọc file JUnit XML → list kết quả từng test.
    """
    xml = JUnitXml.fromfile(junit_path)
    results = []

    for suite in xml:
        for case in suite:
            name = case.name
            status = "pass"
            error_message = ""

            res = case.result
            if isinstance(res, list) and res:
                res = res[0]

            if res:
                t = (res.type or "").lower()
                if "failure" in t:
                    status = "fail"
                elif "error" in t:
                    status = "error"
                elif "skipped" in t:
                    status = "skip"
                error_message = res.message or ""

            exec_time = float(case.time or 0.0)

            results.append(
                {
                    "identifier": name,
                    "status": status,
                    "execution_time": exec_time,
                    "error_message": error_message,
                }
            )

    return results


def post_test_result(api_key, test_phase_id, test_suite_assignment_id,
                     test_cycle_id, user_id, test_case_no, result):
    """
    Gửi 1 kết quả test vào QF.
    """
    url = (
        f"{BASE_URL}/test_phases/{test_phase_id}"
        f"/test_suite_assignments/{test_suite_assignment_id}"
        f"/test_cycles/{test_cycle_id}/test_results.json"
    )

    params = {"api_key": api_key}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    executed_at = datetime.utcnow().isoformat()

    data = {
        "test_result[test_case_no]": test_case_no,
        "test_result[result]": result["status"],      # pass/fail/error/skip
        "test_result[user_id]": user_id,
        "test_result[executed_at]": executed_at,
        # map các cột result (content1/2/3) trong Test Result
        "test_result[content1]": result["identifier"],              # Auto test id
        "test_result[content2]": str(result["execution_time"]),     # time
    }

    if result["error_message"]:
        data["test_result[content3]"] = result["error_message"][:1000]

    resp = requests.post(url, params=params, headers=headers, data=data)
    resp.raise_for_status()


def build_identifier_mapping():
    """
    Mapping giữa tên test method (JUnit) và số thứ tự dòng (No) trong Test Suite QF.
    CHỈ CẦN SỬA HÀM NÀY THEO TEST SUITE CỦA BẠN.
    """
    mapping = {
        "test_add_two_numbers": 1,
        "test_add_negative": 2,
    }
    return mapping


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync JUnit test results to QualityForward Test Cycle."
    )
    parser.add_argument("junit_path", help="Path to JUnit XML (e.g. results/junit.xml)")
    parser.add_argument(
        "-a", "--api-key",
        default=os.getenv("QF_API_KEY"),
        help="QualityForward API key (or env QF_API_KEY)",
    )
    parser.add_argument(
        "--test-phase-id",
        default=os.getenv("QF_TEST_PHASE_ID"),
        help="Test Phase ID (or env QF_TEST_PHASE_ID)",
    )
    parser.add_argument(
        "--test-suite-assignment-id",
        default=os.getenv("QF_TEST_SUITE_ASSIGNMENT_ID"),
        help="Test Suite Assignment ID (or env QF_TEST_SUITE_ASSIGNMENT_ID)",
    )
    parser.add_argument(
        "--user-id",
        default=os.getenv("QF_USER_ID"),
        help="QF user_id (or env QF_USER_ID)",
    )
    parser.add_argument(
        "--target-priorities",
        default=os.getenv("QF_TARGET_PRIORITIES", "A"),
        help="Target priorities (default=A).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.api_key:
        print("ERROR: API key is required. Set QF_API_KEY or use -a.")
        sys.exit(1)
    if not args.test_phase_id or not args.test_suite_assignment_id:
        print("ERROR: test_phase_id and test_suite_assignment_id are required.")
        sys.exit(1)
    if not args.user_id:
        print("ERROR: user_id is required. Set QF_USER_ID or use --user-id.")
        sys.exit(1)

    print("[QF] Creating test cycle...")
    cycle_id = create_test_cycle(
        api_key=args.api_key,
        test_phase_id=args.test_phase_id,
        test_suite_assignment_id=args.test_suite_assignment_id,
        target_priorities=args.target_priorities,
    )
    print(f"[QF] Created test cycle id={cycle_id}")

    print("[QF] Parsing JUnit results...")
    results = parse_junit_results(args.junit_path)
    identifier_to_no = build_identifier_mapping()

    print(f"[QF] Sending {len(results)} test results...")
    for res in results:
        identifier = res["identifier"]
        test_case_no = identifier_to_no.get(identifier)

        if not test_case_no:
            print(f"[QF] Skip (no mapping for Identifier='{identifier}')")
            continue

        print(f"[QF]  -> case_no={test_case_no}, id={identifier}, status={res['status']}")
        post_test_result(
            api_key=args.api_key,
            test_phase_id=args.test_phase_id,
            test_suite_assignment_id=args.test_suite_assignment_id,
            test_cycle_id=cycle_id,
            user_id=args.user_id,
            test_case_no=test_case_no,
            result=res,
        )
        time.sleep(0.5)

    print("[QF] Done.")


if __name__ == "__main__":
    main()
