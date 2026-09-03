from .db import get_cursor


def list_menu_groups():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tbl_users_folder ORDER BY pf_order ASC")
        folders = cur.fetchall()
        cur.execute("SELECT * FROM tbl_users_menu ORDER BY id ASC")
        menus = cur.fetchall()

    menus_by_folder = {}
    for menu in menus:
        menus_by_folder.setdefault(menu["pm_folder_id"], []).append(menu)

    groups = []
    for folder in folders:
        folder_menus = menus_by_folder.get(folder["id"], [])
        if folder_menus:
            groups.append({"folder": folder, "menus": folder_menus})
    return groups
