from story_generator.vocabulary.parser import parse_vocab
import json

class IngestionService:
    def __init__(self, client, repository):
        self.client = client
        self.repository = repository

    def import_list(self, list_id: str):
        list_data = self.client.get_list(list_id)

        imported = 0
        skipped = 0

        list_db_id = self.repository.ensure_list(
            list_data["id"],
            list_data["name"],
        )

        total = len(list_data["vocab_ids"])

        print(f"Importing list '{list_data['name']}' ({total} vocabulary items)...")

        for i, vocab_id in enumerate(list_data["vocab_ids"], start=1):
            if i % 25 == 0 or i == total:
                print(f"  Progress: {i}/{total}")

            vocab_response = self.client.get_vocabs(vocab_id)

            vocab = parse_vocab(vocab_response)

            vocab_db_id = self.repository.ensure_vocab(vocab)

            self.repository.link_vocab_to_list(
                list_db_id,
                vocab_db_id,
            )

        print(f"Finished '{list_data['name']}'.")

        return {
            "imported": imported,
            "skipped": skipped,
        }
    
    def import_all_lists(self):
        lists = self.client.get_lists()

        print(f"Found {len(lists)} lists to import.\n")

        for i, vocab_list in enumerate(lists, start=1):
            print(f"[{i}/{len(lists)}] Importing '{vocab_list['name']}'...")
            self.import_list(vocab_list["id"])

        print("\nAll lists imported.")