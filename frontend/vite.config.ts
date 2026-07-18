import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import createSvgSpritePlugin from "vite-plugin-svg-sprite";
import tsconfigPaths from "vite-tsconfig-paths";

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [
    tailwindcss(),
    reactRouter(),
    tsconfigPaths(),
    createSvgSpritePlugin({
      exportType: "vanilla",
      include: "**/assets/svg/**/*.svg",
      svgo: {
        plugins: [
          {
            name: "preset-default",
            params: {
              overrides: {
                removeViewBox: false,
                removeUnknownsAndDefaults: {
                  keepDataAttrs: false,
                  keepAriaAttrs: true,
                },
                cleanupIds: {
                  minify: true,
                  preserve: [],
                },
                removeUselessStrokeAndFill: false,
              },
            },
          },
          {
            name: "removeAttrs",
            params: {
              attrs: "(data-.*|class)",
              elemSeparator: ",",
            },
          },
          "removeMetadata",
          "removeComments",
          "removeEmptyText",
          "removeEmptyContainers",
          "convertPathData",
          "mergePaths",
          {
            name: "convertColors",
            params: { currentColor: true },
          },
        ],
      },
    }),
  ],

  clearScreen: false,
  server: {
    port: 1420,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  resolve:
    process.env.NODE_ENV === "development"
      ? {}
      : {
          alias: {
            "react-dom/server": "react-dom/server.node",
          },
        },
}));
