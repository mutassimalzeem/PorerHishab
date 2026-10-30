import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LanguageProvider } from "../lib/Language";
import App from "../App";
import { api, setSession } from "../lib/api";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();

  return {
    ...actual,
    setSession: vi.fn(),
    api: {
      ...actual.api,
      login: vi.fn(),
      register: vi.fn(),
      me: vi.fn(),
    },
  };
});

const mockedApi = vi.mocked(api);
const mockedSetSession = vi.mocked(setSession);

function renderApp() {
  return render(
    <LanguageProvider>
      <App />
    </LanguageProvider>,
  );
}

describe("Authentication flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("signs in and opens the protected workspace", async () => {
    const user = userEvent.setup();

    mockedApi.login.mockResolvedValue({
      access_token: "access-token",
      refresh_token: "refresh-token",
      token_type: "bearer",
    });

    mockedApi.me.mockResolvedValue({
      id: 1,
      email: "test@example.com",
      full_name: "Test User",
    });

    renderApp();

    await user.type(
      screen.getByLabelText(/email address/i),
      "test@example.com",
    );
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockedApi.me).toHaveBeenCalledOnce();
    });

    expect(mockedSetSession).toHaveBeenCalledWith({
      access_token: "access-token",
      refresh_token: "refresh-token",
      token_type: "bearer",
    });

    expect(
      await screen.findByText("Test User"),
    ).toBeInTheDocument();
  });

  it("registers without requiring a refresh token", async () => {
    const user = userEvent.setup();

    mockedApi.register.mockResolvedValue({
      access_token: "registration-token",
      token_type: "bearer",
    });

    mockedApi.me.mockResolvedValue({
      id: 2,
      email: "new@example.com",
      full_name: "New User",
    });

    renderApp();

    await user.click(
      screen.getByRole("button", { name: /new here\? create an account/i }),
    );

    await user.type(screen.getByLabelText(/your name/i), "New User");
    await user.type(
      screen.getByLabelText(/email address/i),
      "new@example.com",
    );
    await user.type(screen.getByLabelText(/password/i), "password123");

    await user.click(
      screen.getByRole("button", { name: /create account/i }),
    );

    await waitFor(() => {
      expect(mockedApi.register).toHaveBeenCalledOnce();
      expect(mockedApi.me).toHaveBeenCalledOnce();
    });

    expect(mockedSetSession).toHaveBeenCalledWith({
      access_token: "registration-token",
      token_type: "bearer",
    });
  });

  it("does not open the workspace when identity verification fails", async () => {
    const user = userEvent.setup();

    mockedApi.login.mockResolvedValue({
      access_token: "invalid-token",
      refresh_token: "refresh-token",
      token_type: "bearer",
    });

    mockedApi.me.mockRejectedValue(new Error("Invalid session"));

    renderApp();

    await user.type(
      screen.getByLabelText(/email address/i),
      "test@example.com",
    );
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/invalid session/i)).toBeInTheDocument();

    expect(mockedSetSession).toHaveBeenLastCalledWith(null);
  });
});