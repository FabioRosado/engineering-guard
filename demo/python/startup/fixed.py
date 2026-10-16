def start_index(open_connection, load_index):
    connection = open_connection()
    try:
        index = load_index(connection)
    except Exception as startup_error:
        try:
            connection.close()
        except Exception as cleanup_error:
            raise startup_error from cleanup_error
        raise
    return index, connection
