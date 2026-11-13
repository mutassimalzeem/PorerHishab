import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { AccountRecovery } from "../pages/AccountRecovery";
import { Auth } from "../pages/Auth";
import { LanguageProvider } from "../lib/Language";
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

  it.each([
    { name: "ordinary", password: "replacement-password" },
    { name: "maximum ASCII", password: "L".repeat(1024) },
    {
      name: "maximum Unicode with spaces",
      password: " " + "\u{1f511}".repeat(1022) + " ",
    },
  ])("submits the supplied replacement password: $name", async ({ password }) => {
    window.history.replaceState(
      null,
      "",
      "/reset-password#token=synthetic-reset",
    );
    const confirm = vi
      .spyOn(api, "confirmPasswordReset")
      .mockResolvedValue({ message: "Password updated." });
    render(<AccountRecovery mode="reset-password" />);
    expect(screen.getByLabelText(/New password/)).not.toHaveAttribute("maxlength");
    fireEvent.change(screen.getByLabelText(/New password/), {
      target: { value: password },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(confirm).toHaveBeenCalledWith("synthetic-reset", password),
    );
  });
});


it.each([false, true])("preserves long Unicode passwords at auth (register=%s)", async (register) => {
  const password = " " + "\u{1f511}".repeat(1022) + " ";
  const tokens = { access_token: "synthetic-access", token_type: "bearer" };
  const login = vi.spyOn(api, "login").mockResolvedValue(tokens);
  const create = vi.spyOn(api, "register").mockResolvedValue(tokens);
  const onLogin = vi.fn();
  render(
    <LanguageProvider>
      <Auth expired={false} onLogin={onLogin} />
    </LanguageProvider>,
  );
  if (register) {
    fireEvent.click(
      screen.getByRole("button", { name: /New here.*Create an account/i }),
    );
  }
  const input = screen.getByLabelText(/^Password/);
  expect(input).not.toHaveAttribute("maxlength");
  fireEvent.change(screen.getByLabelText(/Email address/), {
    target: { value: "synthetic@example.com" },
  });
  fireEvent.change(input, { target: { value: password } });
  fireEvent.click(
    screen.getByRole("button", {
      name: register ? /^Create account/ : /^Sign in/,
    }),
  );
  await waitFor(() => expect(onLogin).toHaveBeenCalledWith(tokens));
  if (register) {
    expect(create).toHaveBeenCalledWith("synthetic@example.com", password, "");
  } else {
    expect(login).toHaveBeenCalledWith("synthetic@example.com", password);
  }
});
