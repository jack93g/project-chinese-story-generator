import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { StoryQuiz } from "./story-quiz";

const { flagQuestion, submitQuizAttempt } = vi.hoisted(() => ({
  flagQuestion: vi.fn(),
  submitQuizAttempt: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>(
    "@/lib/api",
  );
  return { ...actual, flagQuestion, submitQuizAttempt };
});

const QUESTIONS = [
  { question: "他们去哪里？", options: ["学校", "饭馆", "商店"] },
  { question: "他们做什么？", options: ["点菜", "看书"] },
];

const MARKED = {
  id: 1,
  correct_count: 1,
  question_count: 2,
  results: [
    { selected: 1, answer: 1, correct: true, evidence: "他们去饭馆吃饭。" },
    { selected: 1, answer: 0, correct: false, evidence: null },
  ],
};

function answerBoth() {
  fireEvent.click(screen.getByRole("radio", { name: "饭馆" }));
  fireEvent.click(screen.getByRole("radio", { name: "看书" }));
}

describe("StoryQuiz", () => {
  afterEach(() => vi.resetAllMocks());

  it("shows each question with its options", () => {
    render(<StoryQuiz storyId={5} questions={QUESTIONS} />);

    expect(
      screen.getByRole("group", { name: "他们去哪里？" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(5);
  });

  it("can't be checked until every question is answered", () => {
    render(<StoryQuiz storyId={5} questions={QUESTIONS} />);
    const check = screen.getByRole("button", { name: "Check answers" });

    expect(check).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "饭馆" }));
    expect(check).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "看书" }));
    expect(check).toBeEnabled();
  });

  it("sends the chosen options and shows the marked answers", async () => {
    submitQuizAttempt.mockResolvedValue(MARKED);
    render(<StoryQuiz storyId={5} questions={QUESTIONS} />);

    answerBoth();
    fireEvent.click(screen.getByRole("button", { name: "Check answers" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "1 of 2 correct",
    );
    expect(submitQuizAttempt).toHaveBeenCalledWith(5, [1, 1]);
    expect(screen.getByRole("radio", { name: "饭馆 ✓ Correct" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "点菜 ✓ Answer" })).toBeDisabled();
    expect(
      screen.getByRole("radio", { name: "看书 ✗ Your answer" }),
    ).toBeDisabled();
  });

  it("starts over on try again", async () => {
    submitQuizAttempt.mockResolvedValue(MARKED);
    render(<StoryQuiz storyId={5} questions={QUESTIONS} />);
    answerBoth();
    fireEvent.click(screen.getByRole("button", { name: "Check answers" }));
    await screen.findByRole("status");

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText(/Correct|Your answer/)).not.toBeInTheDocument();
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).not.toBeChecked();
      expect(radio).toBeEnabled();
    }
    expect(screen.getByRole("button", { name: "Check answers" })).toBeDisabled();
  });

  it("says so and keeps the answers when checking fails", async () => {
    submitQuizAttempt.mockRejectedValue(
      new ApiError("Story 5 has no comprehension questions", 404),
    );
    render(<StoryQuiz storyId={5} questions={QUESTIONS} />);

    answerBoth();
    fireEvent.click(screen.getByRole("button", { name: "Check answers" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Story 5 has no comprehension questions",
    );
    expect(screen.getByRole("radio", { name: "饭馆" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Check answers" })).toBeEnabled();
  });

  async function renderMarked() {
    submitQuizAttempt.mockResolvedValue(MARKED);
    render(<StoryQuiz storyId={5} questions={QUESTIONS} />);
    answerBoth();
    fireEvent.click(screen.getByRole("button", { name: "Check answers" }));
    await screen.findByText("1 of 2 correct");
  }

  it("shows the sentence that settles each answer once marked", async () => {
    render(<StoryQuiz storyId={5} questions={QUESTIONS} />);
    expect(screen.queryByText(/The story says/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "This question seems wrong" }),
    ).not.toBeInTheDocument();

    submitQuizAttempt.mockResolvedValue(MARKED);
    answerBoth();
    fireEvent.click(screen.getByRole("button", { name: "Check answers" }));

    expect(await screen.findByText("他们去饭馆吃饭。")).toBeInTheDocument();
    // Only the first question has evidence.
    expect(screen.getAllByText(/The story says/)).toHaveLength(1);
  });

  it("reports a question once, even after trying again", async () => {
    flagQuestion.mockResolvedValue({ id: 9 });
    await renderMarked();

    fireEvent.click(
      screen.getAllByRole("button", { name: "This question seems wrong" })[1],
    );

    expect(await screen.findByText("Reported. Thanks!")).toBeInTheDocument();
    expect(flagQuestion).toHaveBeenCalledWith(5, 1);
    expect(
      screen.getAllByRole("button", { name: "This question seems wrong" }),
    ).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    answerBoth();
    fireEvent.click(screen.getByRole("button", { name: "Check answers" }));

    expect(await screen.findByText("Reported. Thanks!")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "This question seems wrong" }),
    ).toHaveLength(1);
  });

  it("says so and lets you retry when reporting fails", async () => {
    flagQuestion.mockRejectedValue(new TypeError("Failed to fetch"));
    await renderMarked();

    fireEvent.click(
      screen.getAllByRole("button", { name: "This question seems wrong" })[0],
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn’t report it. Try again.",
    );
    expect(
      screen.getAllByRole("button", { name: "This question seems wrong" })[0],
    ).toBeEnabled();
  });
});
