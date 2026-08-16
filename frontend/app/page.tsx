import { CreateMessage } from "@/components/studio/CreateMessage";

/**
 * Create Message is the front door. There is no separate landing page: a tester who opens
 * the app is already on the screen that does the job they came to do.
 */
export default function CreateMessagePage() {
  return <CreateMessage />;
}
