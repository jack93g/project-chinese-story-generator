import argparse
import sys
from collections.abc import Sequence

from sqlalchemy.orm import Session

from story_generator.database.session import get_session_factory
from story_generator.stories.persistence.repository import StoryRepository
from story_generator.stories.review import QuestionReview, QuestionReviewService
from story_generator.stories.service import StoryHasNoQuizError, StoryNotFoundError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review the comprehension questions readers have flagged "
        "as seeming wrong. Questions are numbered from 1, as the reader shows "
        "them."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("flagged", help="Every flagged question, most flagged first.")
    show = commands.add_parser(
        "show", help="A story's text and all its questions, to judge one in context."
    )
    show.add_argument("story_id", type=int, metavar="STORY_ID")

    return parser


def _format(review: QuestionReview, with_story: bool) -> str:
    question = review.question
    heading = f"Q{review.index + 1}"
    if with_story:
        heading = f"Story {review.story_id} · {review.story_title} · {heading}"
    if review.flag_count:
        heading += (
            f" · flagged {review.flag_count}x, last {review.last_flagged_at:%Y-%m-%d}"
        )
    lines = [heading, f"  {question['question']}"]
    for index, option in enumerate(question["options"]):
        mark = "✓" if index == question["answer"] else " "
        lines.append(f"    {mark} {option}")
    if question.get("evidence"):
        lines.append(f"  Evidence: {question['evidence']}")
    if review.attempt_count:
        lines.append(
            f"  Answered right in {review.correct_count} of "
            f"{review.attempt_count} attempts"
        )
    else:
        lines.append("  Not answered yet")
    return "\n".join(lines)


def run(argv: Sequence[str], session: Session) -> str:
    """Execute one command. Returns the text to print; changes nothing."""
    args = build_parser().parse_args(argv)
    service = QuestionReviewService(StoryRepository(session))

    if args.command == "flagged":
        reviews = service.flagged()
        if not reviews:
            return "No questions have been flagged."
        return "\n\n".join(_format(review, with_story=True) for review in reviews)

    story, reviews = service.story(args.story_id)
    return "\n\n".join(
        [
            f"Story {story.id} · {story.title}",
            story.content,
            *(_format(review, with_story=False) for review in reviews),
        ]
    )


def main() -> None:
    session = get_session_factory()()
    try:
        print(run(sys.argv[1:], session))
    except (StoryNotFoundError, StoryHasNoQuizError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
