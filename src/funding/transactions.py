from sqlalchemy import text


def lock_change_log(session):
    """Serialize SQL Server change IDs through commit, preventing missed incremental events."""
    if session.bind.dialect.name != "mssql":
        return  # SQLite already serializes writers.
    transaction = session.get_transaction()
    if session.info.get("change_log_transaction") is transaction:
        return
    result = session.execute(text("""DECLARE @result int;
        EXEC @result = sys.sp_getapplock @Resource='funding-change-log',
        @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=30000;
        SELECT @result;""")).scalar()
    if result is None or result < 0:
        raise RuntimeError("Could not acquire transaction lock for change log")
    session.info["change_log_transaction"] = transaction
