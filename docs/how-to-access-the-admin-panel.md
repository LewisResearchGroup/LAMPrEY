# How to access the admin panel?

If you followed the steps in the [installation](installation.md) you
have already created an admin account and started the LAMPrEY server.

Use a web browser and navigate to your local server or your deployed domain.
For local setups this is usually [http://localhost:8000](http://localhost:8000) in development mode or [http://localhost:8080](http://localhost:8080) in production-style mode.

The admin page can be accessed using two methods, one using the `ADMIN` button:

![](img/admin-button.png)

or by login into the admin page through the URL [http://localhost:8000/admin](http://localhost:8000/admin) for development or [http://localhost:8080/admin](http://localhost:8080/admin) for production.

![](img/login.png)

After successful login the following view opens.

![](img/admin-panel.png)

This is the admin panel where users, projects, pipelines, and related resources can be managed.

## What belongs under the admin panel

The admin panel is where the platform structure is created and maintained.

Use it when you need to:

- [add a user](how-to-add-a-user.md)
- [create a project](how-to-add-a-project.md)
- [prepare `mqpar.xml`](how-to-prepare-mqpar.md)
- [create a pipeline](how-to-add-a-pipeline.md)
- [submit RAW files](how-to-submit-raw-files.md) after a pipeline has been configured

This matches the architecture where administrative configuration feeds the operational views in **Main** and the analytical views in **Dashboard**.
