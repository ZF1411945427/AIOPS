import os, time
db_path = r"D:\AIOPS\project07\docker\milvus\kb_v2.db"
lock_path = db_path + ".lock"
for p in [lock_path, db_path]:
    if os.path.exists(p):
        try:
            os.remove(p)
            print(f"Deleted: {p}")
        except PermissionError:
            # rename then delete
            tmp = p + ".old"
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
                os.rename(p, tmp)
                print(f"Renamed: {p} -> {tmp}")
            except Exception as e:
                print(f"Cannot remove {p}: {e}")
    else:
        print(f"Not found: {p}")
print("Done")
