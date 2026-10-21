import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { FieldError, FieldHint, Label } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { AuthLayout } from '@/features/auth/login-page'
import { useSession } from '@/features/auth/session-provider'
import { ApiError } from '@/lib/api-client'

const schema = z.object({
  display_name: z.string().min(1, 'Enter your name').max(120),
  email: z.email('Enter a valid email address'),
  password: z
    .string()
    .min(10, 'Use at least 10 characters')
    .regex(/[A-Za-z]/, 'Include at least one letter')
    .regex(/\d/, 'Include at least one digit'),
})

type FormValues = z.infer<typeof schema>

export function RegisterPage() {
  const { signUp } = useSession()
  const navigate = useNavigate()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { display_name: '', email: '', password: '' },
  })

  async function onSubmit(values: FormValues) {
    try {
      await signUp(values)
      navigate('/')
    } catch (error) {
      if (error instanceof ApiError) {
        const policy = error.details?.password_policy
        if (Array.isArray(policy) && policy.length > 0) {
          setError('password', { message: `Password ${String(policy[0])}` })
        }
        setError('root', { message: error.message })
        return
      }
      setError('root', { message: 'Unexpected error. Please try again.' })
    }
  }

  return (
    <AuthLayout
      title="Create your AgentOps account"
      subtitle="You will create a workspace next - every agent, workflow and trace lives inside it."
    >
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
          <Label htmlFor="display_name" required>
            Full name
          </Label>
          <Input
            id="display_name"
            autoComplete="name"
            invalid={Boolean(errors.display_name)}
            {...register('display_name')}
          />
          <FieldError>{errors.display_name?.message}</FieldError>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="email" required>
            Work email
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
            autoComplete="new-password"
            invalid={Boolean(errors.password)}
            {...register('password')}
          />
          <FieldError>{errors.password?.message}</FieldError>
          <FieldHint>At least 10 characters, including a letter and a digit.</FieldHint>
        </div>

        <Button type="submit" className="w-full" loading={isSubmitting}>
          Create account
        </Button>

        <p className="text-center text-xs text-[var(--muted-foreground)]">
          Already registered?{' '}
          <Link to="/login" className="text-[var(--primary)] hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
