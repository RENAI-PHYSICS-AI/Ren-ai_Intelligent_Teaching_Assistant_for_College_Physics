from __future__ import annotations

from getpass import getpass

import analytics_db


def main() -> None:
    analytics_db.init_db()
    initial_password = getpass("教师账号初始密码：")
    confirmation = getpass("再次输入初始密码：")
    if initial_password != confirmation:
        raise SystemExit("两次输入的密码不一致，未修改数据库。")
    created = analytics_db.provision_unbound_teacher_accounts(initial_password)
    print(f"已创建并绑定 {len(created)} 个教师账号。")
    for account in created:
        print(f"{account['institutional_id']}\t{account['real_name']}")


if __name__ == "__main__":
    main()
