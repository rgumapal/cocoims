import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // reference data (items, locations, refdata) doesn't change every second
      retry: 1,
    },
  },
});
