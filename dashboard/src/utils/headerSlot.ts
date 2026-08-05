import { createContext, useContext, type ReactNode } from "react";

/**
 * A single slot in the middle of the global header that a page can fill.
 *
 * The header lives in the app Layout, but its centre content (e.g. the device
 * switcher on a device detail page) is owned by the page. A page publishes into
 * the slot with `setCenter` and clears it on unmount; the Layout renders
 * whatever is there.
 */
interface HeaderSlot {
  center: ReactNode;
  setCenter: (node: ReactNode) => void;
}

export const HeaderSlotContext = createContext<HeaderSlot>({
  center: null,
  setCenter: () => {},
});

export const useHeaderSlot = () => useContext(HeaderSlotContext);
