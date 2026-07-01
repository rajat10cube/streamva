import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createNote, deleteNote, getNotes } from "@/api";

function fmt(s: number): string {
  const t = Math.floor(s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

export default function Notes({
  lectureId,
  getTime,
  onSeek,
}: {
  lectureId: number;
  getTime: () => number;
  onSeek: (t: number) => void;
}) {
  const qc = useQueryClient();
  const { data: notes } = useQuery({ queryKey: ["notes", lectureId], queryFn: () => getNotes(lectureId) });
  const [text, setText] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["notes", lectureId] });

  const add = async () => {
    const t = text.trim();
    if (!t) return;
    await createNote(lectureId, Math.floor(getTime()), t).catch(() => {});
    setText("");
    refresh();
  };
  const remove = async (id: number) => {
    await deleteNote(id).catch(() => {});
    refresh();
  };

  return (
    <Card className="mt-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Notes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void add();
          }}
        >
          <Input
            placeholder="Add a note at the current timestamp…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Button type="submit" disabled={!text.trim()}>Add</Button>
        </form>

        {notes && notes.length > 0 ? (
          <ul className="divide-y rounded-md border">
            {notes.map((n) => (
              <li key={n.id} className="flex items-start gap-3 px-3 py-2">
                <button
                  onClick={() => onSeek(n.positionSec)}
                  className="mt-0.5 shrink-0 rounded bg-primary/15 px-1.5 py-0.5 text-xs font-medium tabular-nums text-primary transition-colors hover:bg-primary/25"
                  title="Jump to this time"
                >
                  {fmt(n.positionSec)}
                </button>
                <span className="flex-1 whitespace-pre-wrap text-sm">{n.text}</span>
                <button
                  onClick={() => void remove(n.id)}
                  className="shrink-0 text-muted-foreground transition-colors hover:text-destructive"
                  title="Delete note"
                >
                  <Trash2 className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No notes yet — type above and it's saved at the current playback time.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
