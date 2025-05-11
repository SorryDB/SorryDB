from prefect import flow, get_run_logger, task


@task
def say_hello_task(name: str) -> str:
    """A simple task that returns a greeting."""
    logger = get_run_logger()
    greeting = f"Hello, {name} from Prefect!"
    logger.info(greeting)
    return greeting


@flow(name="Hello Prefect World")
def hello_prefect_flow(user_name: str = "World"):
    """
    A simple Prefect flow that greets a user.
    """
    logger = get_run_logger()
    logger.info(f"Starting the hello flow for {user_name}...")
    say_hello_task.submit(name=user_name)
    logger.info("Hello flow finished.")


if __name__ == "__main__":
    hello_prefect_flow(user_name="Test User")
