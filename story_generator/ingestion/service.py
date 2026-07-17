from story_generator.vocabulary.parser import parse_vocab


class IngestionService:
    def __init__(self, client, repository):
        self.client = client
        self.repository = repository

    def import_list(self, list_id: str):
        response = self.client.get_list(list_id)

        vocab_ids = response["VocabList"]["vocab_ids"]

        for vocab_id in vocab_ids:
            vocab_response = self.client.get_vocabs(vocab_id)

            vocab = parse_vocab(vocab_response)

            self.repository.insert_vocab(vocab)