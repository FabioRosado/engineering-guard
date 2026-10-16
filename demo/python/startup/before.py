def start_index(open_connection, load_index):
    connection = open_connection()
    index = load_index(connection)
    return index, connection
