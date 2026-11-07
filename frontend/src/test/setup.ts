import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
afterEach(() => {
  cleanup();
});

Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
  configurable: true,
  value: function () {
    this.setAttribute("open", "");
  },
});
Object.defineProperty(HTMLDialogElement.prototype, "close", {
  configurable: true,
  value: function () {
    this.removeAttribute("open");
  },
});

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  writable: true,
  value: function (this: HTMLCanvasElement, contextId = "2d") {
    if (contextId !== "2d") {
      return null;
    }
    return {
      canvas: this,
      font: "",
      textAlign: "start",
      textBaseline: "alphabetic",
      measureText: (text: string) => ({ width: text.length * 10 }),
      fillText: () => {},
      getImageData: (...args: number[]) => {
        const sw = args[2] ?? 1;
        const sh = args[3] ?? 1;
        return {
          data: new Uint8ClampedArray(
            Math.max(1, Math.floor(sw)) * Math.max(1, Math.floor(sh)) * 4,
          ),
        };
      },
      fillRect: () => {},
      clearRect: () => {},
      putImageData: () => {},
      createImageData: () => [],
      setTransform: () => {},
      drawImage: () => {},
      save: () => {},
      restore: () => {},
      beginPath: () => {},
      moveTo: () => {},
      lineTo: () => {},
      closePath: () => {},
      stroke: () => {},
      translate: () => {},
      scale: () => {},
      rotate: () => {},
      arc: () => {},
      fill: () => {},
      transform: () => {},
      rect: () => {},
      clip: () => {},
    };
  },
});

Object.defineProperty(window, "matchMedia", {
  configurable: true,
  writable: true,
  value: (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
  }),
});
