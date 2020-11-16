import catan_messaging_from_jsettlers_py_file_v3 as dqn
import pandas as pd
import random
import socket
import os
from datetime import datetime


class GamePregenerator():
    def __init__(self, host, port, save_directory=None, save_interval=100, split_interval=1000, timeout=None):
        """
        Initialized pre-generator
        :param host: host JSettlers is running at.
        :param port: port to send messages to.
        :param save_directory: Directory to save game logs to. Default: YYYYmmdd_HHMMSS_game_logs
        :param save_interval: Number of games to build up in pandas structure before saving out to csv. Default: 100
        :param split_interval: Number of games to save per file. Default: 1000
        :param timeout: Number of seconds to wait for message from server before timing out.
        """
        self.host = host
        self.port = port
        self.save_interval = save_interval
        self.split_interval = split_interval
        self.timeout = timeout

        if save_directory is None:
            self.save_directory = datetime.now().strftime("%Y%m%d_%H%M%S") + "_game_logs"
        else:
            self.save_directory = save_directory

        self.file_prefix = "game_log_"
        self.file_extension = ".csv"
        self.output_file = None
        self.file_number = 0
        self.games_in_file = 0

        if not os.path.exists(self.save_directory):
            os.mkdir(self.save_directory)

        self.create_new_file()

        self.incomplete_games = 0
        self.unsaved_games = pd.DataFrame(columns=["firstPlacementMessage",
                                                   "firstPlacementChoice",
                                                   "secondPlacementMessage",
                                                   "secondPlacementChoice",
                                                   "endMessage"],
                                          dtype=str)



    def create_new_file(self):
        """
        Creates a new log file.
        :return: None
        """
        self.file_number += 1
        self.output_file = os.path.join(self.save_directory, self.file_prefix + str(self.file_number) + self.file_extension)
        self.games_in_file = 0
        with open(self.output_file, 'w') as fp:
            pass

    def write_to_file(self):
        """
        Writes contents of pandas datastore to file, and resets pandas datastore.
        :return: None
        """
        if (self.games_in_file + self.unsaved_games.shape[0]) > self.split_interval:
            self.create_new_file()

        self.unsaved_games.to_csv(self.output_file, mode='a', header=False, index=False)
        self.games_in_file += self.unsaved_games.shape[0]
        self.unsaved_games = self.unsaved_games[0:0]

    def save_msg(self, msg):
        """
        Saves a history of a game to the pandas datastore.
        :param msg: List of messages, in the form:
            [END_MESSAGE, SETTLEMENT_1_MESSAGE, SETTLEMENT_1_ACTION, SETTLEMENT_2_MESSAGE, SETTLEMENT_2_ACTION]
        :return: None
        """
        if len(msg) == 5:
            new_row = pd.Series(msg[1:] + [msg[0]], index=self.unsaved_games.columns)
            self.unsaved_games = self.unsaved_games.append(new_row, ignore_index=True)
            if self.unsaved_games.shape[0] >= self.save_interval:
                self.write_to_file()
        else:
            print("Incomplete message, not saving...")

    def get_action(self, node_validity):
        """
        LEGACY. Functionality has been moved to JSettlers server, triggered by sending a "random_settlement" response in
        place of a coordinate.
        Generates a random action.
        :param node_validity: Array of valid nodes, generated from init_settlement message.
        :return: Chosen coordinate, as a base 10 integer.
        """
        available_filter = dqn.availability_filter(node_validity)
        possible_actions = []
        for index, validity in enumerate(available_filter):
            if validity == 1:
                possible_actions.append(index)
        action = random.choice(possible_actions)

        java_action = dqn.action_to_255(action)
        return java_action

    def handle_msg(self, msg):
        """
        Handles a message from the JSettlers server. Either takes an action or stores the game history.
        :param msg: Message from JSettlers server.
        :return: Action taken, either "random_settlement" or a coordinate if message is init_settlement, or None if end
        message.
        """
        msg_history = []
        if not "end|" in msg:
            msg_args = msg.split("|")
        else:
            msg_history = msg.split("||")
            msg_args = msg_history[0].split("|")

        if msg_args[0] == "init_settlement":
            return "random_settlement"

        elif msg_args[0] == "end":
            if msg_args[1] == "true":
                self.save_msg(msg_history)
            else:
                self.incomplete_games += 1
                print("Incomplete game (total: {}), ignoring...".format(self.incomplete_games))

        else:
            print("Unexpected message received, ignoring...")

        return None

    def run(self):
        """
        Main function.
        :return: None
        """
        soc = socket.socket()  # Create a socket object
        if self.timeout:
            soc.settimeout(self.timeout)
        try:
            soc.bind((self.host, self.port))

        except socket.error as err:
            print('Bind failed. Error Code : '.format(err))

        soc.listen(10)
        print("Socket Listening ... ")
        while True:
            try:
                conn, addr = soc.accept()  # Establish connection with client.
                length_of_message = int.from_bytes(conn.recv(2), byteorder='big')
                msg = conn.recv(length_of_message).decode("UTF-8")
                print("Message Received ... ")
                action = self.handle_msg(msg)
                if not "end|" in msg:
                    conn.send((str(action) + '\n').encode(encoding='UTF-8'))
            except socket.timeout:
                print("Timeout or error occured. Exiting ... ")
                self.write_to_file()
                break


if __name__ == "__main__":
    server = GamePregenerator("localhost", 2004, timeout=120)
    server.run()
