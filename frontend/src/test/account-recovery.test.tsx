import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { AccountRecovery } from "../pages/AccountRecovery";
import { api } from "../lib/api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

describe("mailbox challenge pages", () => {
  it("removes the token from the URL and confirms only after an explicit action", async () => {
    window.history.replaceState(
      null,
      "",
      "/verify-email#token=synthetic-challenge",
    );
    const confirm = vi
      .spyOn(api, "confirmEmailVerification")
      .mockResolvedValue({ message: "Email verified." });
    render(<AccountRecovery mode="verify-email" />);
    expect(window.location.hash).toBe("");
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(confirm).toHaveBeenCalledWith("synthetic-challenge"),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Email verified.",
    );
  });

  it("does not submit a missing challenge", () => {
    render(<AccountRecovery mode="reset-password" />);
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });

  it("submits the supplied replacement password", async () => {
    window.history.replaceState(
      null,
      "",
      "/reset-password#token=synthetic-reset",
    );
    const confirm = vi
      .spyOn(api, "confirmPasswordReset")
      .mockResolvedValue({ message: "Password updated." });
    render(<AccountRecovery mode="reset-password" />);
    fireEvent.change(screen.getByLabelText(/New password/), {
      target: { value: "replacement-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(confirm).toHaveBeenCalledWith(
        "synthetic-reset",
        "replacement-password",
      ),
    );
  });
});
