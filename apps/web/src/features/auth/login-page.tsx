import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { FieldError, FieldHint, Label } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useSession } from '@/features/auth/session-provider'
import { ApiError } from '@/lib/api-client'

const schema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
})

type FormValues = z.infer<typeof schema>

export function LoginPage() {
  const { signIn, isAuthenticated, configurationError } = useSession()
  const navigate = useNavigate()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } })

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  async function onSubmit(values: FormValues) {
    try {
      await signIn(values.email, values.password)
      navigate('/')
    } catch (error) {
      if (error instanceof ApiError) {
        setError('root', { message: error.message })
        return
      }
      if (error instanceof Error && error.message) {
        setError('root', { message: error.message })
        return
      }
      setError('root', { message: 'Unexpected error. Please try again.' })
    }
  }

  return (
    <AuthLayout
      title="Sign in to AgentOps"
      subtitle="Build, run and govern AI agents with observable, controllable execution."
    >
      {configurationError ? (
        <div
          className="mb-4 rounded-md border border-[var(--warning)]/30 bg-[var(--warning-muted)] px-3 py-2 text-xs text-[var(--warning)]"
          role="alert"
        >
          {configurationError}
        </div>
      ) : null}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {errors.root?.message ? (
          <div
            className="rounded-md border border-[var(--danger)]/30 bg-[var(--danger-muted)] px-3 py-2 text-xs text-[var(--danger)]"
            role="alert"
          >
            {errors.root.message}
          </div>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="email" required>
            Email
          </Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            invalid={Boolean(errors.email)}
            {...register('email')}
          />
          <FieldError>{errors.email?.message}</FieldError>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password" required>
            Password
          </Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            invalid={Boolean(errors.password)}
            {...register('password')}
          />
          <FieldError>{errors.password?.message}</FieldError>
        </div>

        <Button type="submit" className="w-full" loading={isSubmitting} disabled={Boolean(configurationError)}>
          Sign in
        </Button>

        <p className="text-center text-xs text-[var(--muted-foreground)]">
          No account yet?{' '}
          <Link to="/register" className="text-[var(--primary)] hover:underline">
            Create one
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}

export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-full items-center justify-center bg-[var(--background)] px-4 py-12">
      <div className="w-full max-w-sm animate-in-rise">
        <div className="mb-6 flex items-center gap-2">
          <div className="grid size-8 place-items-center rounded-md bg-[var(--primary)] text-[var(--primary-foreground)]">
            <span className="text-sm font-bold">A</span>
          </div>
          <span className="text-sm font-semibold tracking-tight">AgentOps</span>
        </div>
        <h1 className="text-lg font-semibold tracking-tight text-[var(--foreground)]">{title}</h1>
        <p className="mt-1 mb-6 text-xs text-[var(--muted-foreground)]">{subtitle}</p>
        <div className="surface-card p-5">{children}</div>
        <FieldHint>
          Identity is managed by Supabase Auth. The API verifies every access token
          cryptographically and never trusts a client-supplied user id.
        </FieldHint>
      </div>
    </div>
  )
}
