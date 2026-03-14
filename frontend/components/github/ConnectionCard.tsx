"use client"

import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiPost, apiDelete } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { GitHubConnection } from "@/lib/types"

const connectSchema = z.object({
  repo_url: z.string().url("Must be a valid GitHub repository URL"),
  personal_access_token: z.string().min(1, "Personal access token is required"),
})

type ConnectValues = z.infer<typeof connectSchema>

const STATUS_VARIANTS: Record<
  GitHubConnection["status"],
  "default" | "secondary" | "destructive"
> = {
  connected: "default",
  disconnected: "secondary",
  error: "destructive",
}

export function ConnectionCard({
  connection,
}: {
  connection: GitHubConnection | null
}) {
  const queryClient = useQueryClient()
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [isDisconnecting, setIsDisconnecting] = useState(false)

  const form = useForm<ConnectValues>({
    resolver: zodResolver(connectSchema),
    defaultValues: { repo_url: "", personal_access_token: "" },
  })

  async function onConnect(values: ConnectValues) {
    await apiPost("/api/v1/github/connect", values)
    toast.success("Repository connected successfully")
    queryClient.invalidateQueries({ queryKey: ["github-connection"] })
    form.reset()
  }

  async function handleDisconnect() {
    setIsDisconnecting(true)
    try {
      await apiDelete("/api/v1/github/connection")
      toast.success("Repository disconnected")
      queryClient.invalidateQueries({ queryKey: ["github-connection"] })
      setDisconnectOpen(false)
    } finally {
      setIsDisconnecting(false)
    }
  }

  if (connection) {
    return (
      <>
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Connected Repository</CardTitle>
              <Badge variant={STATUS_VARIANTS[connection.status]}>
                {connection.status}
              </Badge>
            </div>
            <CardDescription>{connection.repo_url}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Default Branch</p>
                <p className="font-medium">{connection.default_branch}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Last Synced</p>
                <p className="font-medium">
                  {connection.last_synced_at
                    ? new Date(connection.last_synced_at).toLocaleString()
                    : "Never"}
                </p>
              </div>
            </div>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setDisconnectOpen(true)}
            >
              Disconnect
            </Button>
          </CardContent>
        </Card>

        <Dialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Disconnect Repository</DialogTitle>
              <DialogDescription>
                This will remove the GitHub connection. Content already synced
                will remain in your knowledge base.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDisconnectOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleDisconnect}
                disabled={isDisconnecting}
              >
                {isDisconnecting ? "Disconnecting…" : "Disconnect"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Connect a Repository</CardTitle>
        <CardDescription>
          Link a GitHub repository to sync content into your knowledge base.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onConnect)} className="space-y-4">
            <FormField
              control={form.control}
              name="repo_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Repository URL</FormLabel>
                  <FormControl>
                    <Input placeholder="https://github.com/org/repo" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="personal_access_token"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Personal Access Token</FormLabel>
                  <FormControl>
                    <Input type="password" placeholder="ghp_…" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button
              type="submit"
              disabled={form.formState.isSubmitting}
            >
              {form.formState.isSubmitting ? "Connecting…" : "Connect"}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  )
}
