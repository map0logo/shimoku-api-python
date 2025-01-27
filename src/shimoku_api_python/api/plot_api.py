""""""
import time
from typing import List, Dict, Optional, Union, Tuple, Any, Iterable, Callable
import json
from itertools import product

from IPython.lib import backgroundjobs as bg

import json5
import datetime as dt
import pandas as pd
import numpy as np
import warnings
from pandas import DataFrame

import uuid
from shimoku_api_python.exceptions import ApiClientError
from .data_managing_api import DataValidation
from .explorer_api import (
    BusinessExplorerApi, CreateExplorerAPI, CascadeExplorerAPI,
    CascadeCreateExplorerAPI, MultiCreateApi,
    AppExplorerApi, ReportExplorerApi,
    DeleteExplorerApi, UniverseExplorerApi,
    ReportDatasetExplorerApi, DatasetExplorerApi,
)
from .data_managing_api import DataManagingApi
from .app_metadata_api import AppMetadataApi
from .app_type_metadata_api import AppTypeMetadataApi
import asyncio

from shimoku_api_python.async_execution_pool import async_auto_call_manager

import logging
from shimoku_api_python.execution_logger import logging_before_and_after
logger = logging.getLogger(__name__)


class PlotAux:
    def __init__(self, api_client, app_metadata_api):
        self.business_explorer_api = BusinessExplorerApi(api_client=api_client)
        self.universe_explorer_api = UniverseExplorerApi(api_client=api_client)
        self.report_explorer_api = ReportExplorerApi(api_client=api_client)
        self.app_explorer_api = AppExplorerApi(api_client=api_client)
        self.cascade_explorer = CascadeExplorerAPI(api_client=api_client)
        self.create_explorer_api = CreateExplorerAPI(api_client=api_client)
        self.cascade_create_explorer_api = CascadeCreateExplorerAPI(api_client=api_client)
        self.report_dataset_explorer_api = ReportDatasetExplorerApi(api_client=api_client)
        self.dataset_explorer_api = DatasetExplorerApi(api_client=api_client)
        self.app_type_metadata_api = AppTypeMetadataApi(api_client=api_client)
        self.app_metadata_api = app_metadata_api
        self.data_managing_api = DataManagingApi(api_client=api_client)
        self.data_validation_api = DataValidation(api_client=api_client)
        self.multi_create_api = MultiCreateApi(api_client=api_client)
        self.delete_explorer_api = DeleteExplorerApi(api_client=api_client)

        self.api_client = api_client

        self.get_business = self.business_explorer_api.get_business
        self.get_business_apps = self.business_explorer_api.get_business_apps
        self.get_business_reports = self.business_explorer_api.get_business_reports

        self.get_universe_businesses = self.universe_explorer_api.get_universe_businesses

        self.get_report = self.report_explorer_api.get_report
        self.get_report_with_data = self.report_explorer_api._get_report_with_data

        self.get_report_data = self.report_explorer_api.get_report_data
        self.update_report = self.report_explorer_api.update_report

        self.update_app = self.app_explorer_api.update_app

        self.find_app_by_name_filter = self.cascade_explorer.find_app_by_name_filter
        self.find_app_type_by_name_filter = self.cascade_explorer.find_app_type_by_name_filter
        # TODO this shit (methods with underscore _* and *) has to be fixed
        self.get_universe_app_types = self.cascade_explorer.get_universe_app_types
        self.get_app_reports = self.cascade_explorer.get_app_reports
        self.get_app_by_type = self.cascade_explorer.get_app_by_type
        self.get_app_by_name = self.cascade_explorer.get_app_by_name
        self.find_business_by_name_filter = self.cascade_explorer.find_business_by_name_filter
        self.get_report_datasets = self.cascade_explorer.get_report_datasets
        self.get_dataset_data = self.cascade_explorer.get_dataset_data
        self.get_report_dataset_data = self.cascade_explorer.get_report_dataset_data

        self.create_report = self.create_explorer_api.create_report
        self.create_app_type = self.create_explorer_api.create_app_type
        self.create_normalized_name = self.create_explorer_api._create_normalized_name
        self.create_key_name = self.create_explorer_api._create_key_name
        self.create_app = self.create_explorer_api.create_app
        self.create_business = self.create_explorer_api.create_business

        self.create_dataset = self.cascade_create_explorer_api.create_dataset

        self.create_reportdataset = self.report_dataset_explorer_api.create_reportdataset
        self.create_report_and_dataset = self.report_dataset_explorer_api.create_report_and_dataset

        self.create_data_points = self.dataset_explorer_api.create_data_points

        self.get_app_type_by_name = self.app_type_metadata_api.get_app_type_by_name
        self.get_or_create_app_and_apptype = self.app_metadata_api.get_or_create_app_and_apptype

        self.update_report_data = self.data_managing_api.update_report_data
        self.append_report_data = self.data_managing_api.append_report_data
        self.transform_report_data_to_chart_data = self.data_managing_api._transform_report_data_to_chart_data
        self.convert_input_data_to_db_items = self.data_managing_api._convert_input_data_to_db_items
        self.is_report_data_empty = self.data_managing_api._is_report_data_empty
        self.convert_dataframe_to_report_entry = self.data_managing_api._convert_dataframe_to_report_entry
        self.create_report_entries = self.data_managing_api._create_report_entries

        self.validate_table_data = self.data_validation_api._validate_table_data
        self.validate_input_form_data = self.data_validation_api._validate_input_form_data
        self.validate_tree_data = self.data_validation_api._validate_tree_data
        self.validate_data_is_pandarable = self.data_validation_api._validate_data_is_pandarable

        self.create_app_type_and_app = self.multi_create_api.create_app_type_and_app

        self.delete_report = self.delete_explorer_api.delete_report
        self.delete_app = self.delete_explorer_api.delete_app
        self.delete_report_entries = self.delete_explorer_api.delete_report_entries


class BasePlot:

    def __init__(self, api_client, app_metadata_api, **kwargs):
        self._plot_aux = PlotAux(api_client, app_metadata_api=app_metadata_api)
        self.api_client = api_client
        self._clear_or_create_all_local_state()

    @logging_before_and_after(logging_level=logger.debug)
    def _clear_or_create_all_local_state(self):
        # Clear or create reports
        # Map to store reports order
        self._report_order = dict()

        # Map to store the link between reports and tab
        self._report_in_tab = dict()

        # Clear or create tabs
        # Tree to store tab plotting information
        self._tabs = dict(dict(list()))

        # Map to store the report_id of each tab
        self._tabs_group_id = dict()

        # Map to store the last order of its reports
        self._tabs_last_order = dict()

        # Map to store tabs properties
        self._tabs_group_properties = dict()

    @logging_before_and_after(logging_level=logger.debug)
    async def _get_business_state(self, business_id: str):

        business_reports = await self._plot_aux.get_business_reports(business_id)

        @logging_before_and_after(logging_level=logger.debug)
        def _get_business_reports_info():
            self._report_order = {report['id']: report['order'] for report in business_reports}

        @logging_before_and_after(logging_level=logger.debug)
        def _get_business_tabs_info():
            business_tabs = [report for report in business_reports if report['reportType'] == 'TABS']

            for tabs_group_report in business_tabs:
                data_fields = json.loads(tabs_group_report['dataFields'].replace("'", '"'))
                properties = json.loads(tabs_group_report['properties'].replace("'", '"'))
                tabs_group_report_id = tabs_group_report['id']
                app_id = tabs_group_report['appId']
                path_name = tabs_group_report['path'] if tabs_group_report['path'] else ""
                last_order = data_fields['lastOrder']
                group_name = data_fields['groupName']
                tabs_group_entry = (app_id, path_name, group_name)

                self._tabs_group_id[tabs_group_entry] = tabs_group_report_id
                self._tabs_last_order[tabs_group_entry] = last_order
                try:
                    tabs_group = properties['tabs']
                    self._tabs_group_properties[tabs_group_entry] = {'sticky': properties['sticky'],
                                                                     'variant': properties['variant']}
                except KeyError:
                    warnings.warn('Tabs group should always have a "tabs" field in properties', RuntimeWarning)
                    continue

                # Order them correctly to preserve insertion order
                tabs_group = dict(sorted(tabs_group.items(), key=lambda item: item[1]['order']))

                self._tabs[tabs_group_entry] = {}
                for tab_name, order_and_report_ids in tabs_group.items():
                    report_ids = order_and_report_ids['reportIds']
                    self._tabs[tabs_group_entry][tab_name] = []
                    for report_id in report_ids:
                        if report_id in self._report_order:
                            self._report_in_tab[report_id] = (app_id, path_name, (group_name, tab_name))
                            self._tabs[tabs_group_entry][tab_name] += [report_id]

        _get_business_reports_info()
        _get_business_tabs_info()

    # TODO this method goes somewhere else (aux.py? an external folder?)
    @staticmethod
    def _convert_to_json(items: List[Dict]) -> str:
        try:
            items_str: str = json.dumps(items)
        except TypeError:
            # If we have date or datetime values
            # then we need to convert them to isoformat
            for datum in items:
                for k, v in datum.items():
                    if isinstance(v, dt.date) or isinstance(v, dt.datetime):
                        datum[k] = v.isoformat()

            items_str: str = json.dumps(items)
        return items_str

    @staticmethod
    def _validate_filters(filters: Dict) -> None:
        # Check the filters is built properly
        try:
            filters = filters.copy()
            if "get_all" in filters.keys():
                del filters["get_all"]

            if filters.get('update_filter_type'):
                cols: List[str] = ['row', 'column', 'filter_cols', 'update_filter_type']
                assert sorted(list(filters.keys())) == sorted(cols)
            else:
                old_cols: List[str] = ['row', 'column', 'filter_cols']
                new_cols: List[str] = ['order', 'filter_cols']
                assert (
                    sorted(list(filters.keys())) == sorted(old_cols)
                    or
                    sorted(list(filters.keys())) == sorted(new_cols)
                )
        except AssertionError:
            raise KeyError(
                f'filters object must contain the keys'
                f'"exists", "row", "column", "filter_cols" | '
                f'Provided keys are: {list(filters.keys())}'
            )

    @staticmethod
    def _validate_bentobox(bentobox_data: Dict) -> None:
        """"""
        # Mandatory fields
        try:
            assert bentobox_data['bentoboxId']
        except AssertionError:
            raise KeyError('bentbox_data must include a "bentoboxId" key')

        # Optional fields
        if bentobox_data.get('bentoboxOrder'):
            try:
                assert bentobox_data['bentoboxOrder'] >= 0
            except AssertionError:
                raise KeyError('bentbox_data must include a "bentoboxOrder" key')
        if bentobox_data.get('bentoboxSizeColumns'):
            try:
                assert bentobox_data['bentoboxSizeColumns'] > 0
            except AssertionError:
                raise ValueError('bentobox_data bentoboxSizeColumns must be a positive integer')
        if bentobox_data.get('bentoboxSizeRows'):
            try:
                assert bentobox_data['bentoboxSizeRows'] > 0
            except AssertionError:
                raise ValueError('bentobox_data bentoboxSizeColumns must be a positive integer')

    @staticmethod
    def _clean_menu_path(menu_path: str) -> Tuple[str, str]:
        """Break the menu path in the apptype or app normalizedName
        and the path normalizedName if any"""
        # remove empty spaces
        menu_path: str = menu_path.strip()
        # replace "_" for www protocol it is not good
        menu_path = menu_path.replace('_', '-')

        try:
            assert len(menu_path.split('/')) <= 2  # we allow only one level of path
        except AssertionError:
            raise ValueError(
                f'We only allow one subpath in your request | '
                f'you introduced {menu_path} it should be maximum '
                f'{"/".join(menu_path.split("/")[:1])}'
            )

        # Split AppType or App Normalized Name
        normalized_name: str = menu_path.split('/')[0]
        name: str = (
            ' '.join(normalized_name.split('-'))
        )

        try:
            path_normalized_name: str = menu_path.split('/')[1]
            path_name: str = (
                ' '.join(path_normalized_name.split('-'))
            )
        except IndexError:
            path_name = None

        return name, path_name

    @staticmethod
    @logging_before_and_after(logging_level=logger.debug)
    def _fill_report_metadata(
            path_name: str, report_metadata: Dict,
            order: Optional[int] = None,
            rows_size: Optional[int] = None,
            cols_size: Optional[int] = None,
            padding: Optional[str] = None,
    ) -> Dict:
        if order is not None and rows_size and cols_size:
            report_metadata['order'] = order
            report_metadata['sizeRows'] = rows_size
            report_metadata['sizeColumns'] = cols_size

        if padding:
            report_metadata['sizePadding'] = padding

        if order is not None:  # elif order fails when order = 0!
            report_metadata['order'] = order
        elif report_metadata.get('grid'):
            report_metadata['order'] = 0
        else:
            raise ValueError(
                'Row and Column or Order must be specified to overwrite a report'
            )

        report_metadata.update({'path': path_name})

        if report_metadata.get('dataFields'):
            report_metadata['dataFields'] = (
                json.dumps(report_metadata['dataFields'])
            )

        return report_metadata

    @logging_before_and_after(logging_level=logger.debug)
    async def _find_target_reports(
            self, menu_path: str,
            grid: Optional[str] = None,
            order: Optional[int] = None,
            component_type: Optional[str] = None,
            by_component_type: bool = True,
            tabs_index: Tuple[str, str] = None,
    ) -> List[Dict]:
        type_map = {
            'alert_indicator': 'INDICATOR',
            'indicator': 'INDICATOR',
            'table': None,
            'stockline': 'STOCKLINECHART',
            'html': 'HTML',
            'MULTIFILTER': 'MULTIFILTER',
            'FORM': 'FORM',
            'TABS': 'TABS',
        }
        if component_type in type_map.keys():
            component_type = type_map[component_type]
        else:
            component_type = 'ECHARTS'

        by_grid: bool = False
        if grid:
            by_grid = True
        elif order is not None:
            pass

        name, path_name = self._clean_menu_path(menu_path=menu_path)

        app: Dict = await self._plot_aux.get_app_by_name(
            business_id=self.business_id,
            name=name,
        )
        app_id: str = app['id']

        reports: List[Dict] = await self._plot_aux.get_app_reports(
            business_id=self.business_id, app_id=app_id,
        )

        # Delete specific components in a path / grid
        # or all of them whatsoever is its component_type
        if by_component_type:
            target_reports: List[Dict] = [
                report
                for report in reports
                if (
                        report['path'] == path_name
                        and report['grid'] == grid
                        and report['reportType'] == component_type
                )
            ]
        elif by_grid:  # Whatever is the reportType delete it
            target_reports: List[Dict] = [
                report
                for report in reports
                if (
                        report['path'] == path_name
                        and report['grid'] == grid
                )
            ]
        elif order is None:
            target_reports: List[Dict] = [
                report
                for report in reports
                if (
                        report['path'] == path_name
                )
            ]
        elif not tabs_index:
            target_reports: List[Dict] = [
                report
                for report in reports
                if (
                        report['path'] == path_name
                        and report['order'] == order
                        and report['id'] not in self._report_in_tab
                        # Don't accept plots inside of tabs even if the order matches
                )
            ]
        else:
            tabs_group_entry = (app_id, path_name if path_name else '', tabs_index[0])
            tab_name = tabs_index[1]
            if tabs_group_entry not in self._tabs or tab_name not in self._tabs[tabs_group_entry]:
                return []
            tab_report_list = self._tabs[tabs_group_entry][tabs_index[1]]
            target_reports: List[Dict] = [
                report
                for report in reports
                if (
                        report['id'] in tab_report_list
                        and report['order'] == order
                )
            ]

        return target_reports

    # TODO unused - deprecate it?
    @logging_before_and_after(logger.info)
    async def _get_component_path_order(self, app_id: str, path_name: str) -> int:
        """Set an ascending report.pathOrder to new path created

        If a report in the same path exists take its path order
        otherwise find the higher report.pathOrder and set it +1
        as the report.pathOrder of the new path
        """
        reports_ = await self._plot_aux.get_app_reports(
            business_id=self.business_id,
            app_id=app_id,
        )

        try:
            order_temp = max([report['pathOrder'] for report in reports_ if report['pathOrder'] ])
        except ValueError:
            order_temp = 0

        path_order: List[int] = [
            report['pathOrder']
            for report in reports_
            if report['path'] == path_name
            if report['pathOrder']
        ]

        if path_order:
            return min(path_order)
        else:
            return order_temp + 1

    # TABS
    @logging_before_and_after(logging_level=logger.debug)
    async def _update_tabs_group_metadata(
            self, business_id: str, app_id: str, path_name: str, group_name: str,
            order: Optional[int] = None, cols_size: Optional[str] = None,
            bentobox_data: Optional[Dict] = None, padding: Optional[str] = None,
            rows_size: Optional[int] = None, just_labels: Optional[bool] = None, sticky: Optional[bool] = None
    ):
        """Updates the tabs report metadata"""
        tabs_group_entry = (app_id, path_name, group_name)
        report_metadata: Dict[str, Any] = {}
        report_id = self._tabs_group_id[tabs_group_entry]
        if bentobox_data:
            report_metadata['bentobox'] = json.dumps(bentobox_data)
        if rows_size:
            report_metadata['sizeRows'] = rows_size
        if cols_size:
            report_metadata['sizeColumns'] = cols_size
        if padding:
            report_metadata['sizePadding'] = padding
        if order:
            report_metadata['order'] = order
            self._report_order[report_id] = order
        if isinstance(just_labels, bool):
            self._tabs_group_properties[tabs_group_entry]['variant'] = 'solidRounded' if just_labels else 'enclosedSolidRounded'
        if isinstance(sticky, bool):
            self._tabs_group_properties[tabs_group_entry]['sticky'] = sticky

        report_metadata['dataFields'] = '{"groupName": "' + group_name + '", "lastOrder": ' + \
                                        str(self._tabs_last_order[tabs_group_entry])+'}'
        tabs = json.dumps(
            {tab_name: {'order': index, 'reportIds': report_ids_list}
             for index, (tab_name, report_ids_list) in enumerate(self._tabs[tabs_group_entry].items())})

        tabs_group_properties = self._tabs_group_properties[tabs_group_entry]
        report_metadata['properties'] = '{"tabs":' + tabs + \
                                        ', "variant": "' + tabs_group_properties['variant'] + '"' \
                                        ', "sticky": ' + ('true' if tabs_group_properties['sticky'] else 'false')+ '}'

        await self._plot_aux.update_report(
            business_id=business_id,
            app_id=app_id,
            report_id=report_id,
            report_metadata=report_metadata,
        )

    @logging_before_and_after(logging_level=logger.debug)
    async def _create_tabs_group(self, business_id: str, tabs_group_entry: Tuple[str, str, str]):
        """Creates a tab report and stores its id"""
        app_id, path_name, group_name = tabs_group_entry

        report_metadata: Dict[str, Any] = {
            'dataFields': "{'groupName': '" + group_name + "', 'lastOrder': 0 }",
            'path': path_name if path_name != "" else None,
            'order': 0,
            'reportType': 'TABS',
            'properties': '{}'
        }
        report: Dict = await self._plot_aux.create_report(
            business_id=business_id,
            app_id=app_id,
            report_metadata=report_metadata,
        )
        self._report_order[report['id']] = 0
        self._tabs_last_order[tabs_group_entry] = 0
        self._tabs_group_id[tabs_group_entry] = report['id']
        self._tabs[tabs_group_entry] = {}
        self._tabs_group_properties[tabs_group_entry] = {'sticky': 'false', 'variant': 'enclosedSolidRounded'}

    @logging_before_and_after(logging_level=logger.debug)
    def _delete_tabs_group(self, tabs_group_entry: Tuple[str, str, str]):
        """Given a tabs_group_entry deletes all the information related to it in the tabs data structures"""
        del self._tabs[tabs_group_entry]
        del self._tabs_last_order[tabs_group_entry]
        self._report_in_tab = {report_id: (app_id, path_name, (group_name, tab_name))
                               for report_id, (app_id, path_name, (group_name, tab_name)) in self._report_in_tab.items()
                               if (app_id, path_name, group_name) != tabs_group_entry}
        if self._tabs_group_id.get(tabs_group_entry):
            del self._tabs_group_id[tabs_group_entry]

    @logging_before_and_after(logging_level=logger.debug)
    def _delete_report_id_from_tab(self, report_id: str):
        """Given a report_id it is deleted from all the data structures of tabs
           :report_id: report UUID
        """
        tab_entry = self._report_in_tab[report_id]
        app_id, path_name, (group_name, tab_name) = tab_entry
        tab_group_entry = (app_id, path_name, group_name)

        removed_report_list = [report for report in self._tabs[tab_group_entry][tab_name]
                               if report != report_id]
        self._tabs[tab_group_entry][tab_name] = removed_report_list

        del self._report_in_tab[report_id]

    @logging_before_and_after(logging_level=logger.debug)
    async def _insert_in_tab(self, business_id: str, app_id: str, path_name: str,
                             report_id: str, tabs_index: Tuple[str, str],
                             order_of_chart: int):
        """This function creates an entry on the tabs tree. If there exists another chart in the same order in the tab
         as the one being created it returns its report_id, if not it returns None"""

        if not path_name:
            path_name = ""

        group, tab = tabs_index

        if not isinstance(group, str) or not isinstance(tab, str):
            raise TypeError("Tabs indexing data must be of the type 'str'.")

        if self._report_in_tab.get(report_id):
            warnings.warn("A report can only be included in one tab.", RuntimeWarning)
            return

        tabs_group_entry = (app_id, path_name, group)
        tab_entry = (app_id, path_name, tabs_index)

        if tabs_group_entry not in self._tabs:
            await self._create_tabs_group(business_id, tabs_group_entry)

        self._report_in_tab[report_id] = tab_entry

        if len(self._tabs.get(tabs_group_entry)) == 0:
            self._tabs[tabs_group_entry] = {tab: [report_id]}
            self._tabs_last_order[tabs_group_entry] = order_of_chart
            await self._update_tabs_group_metadata(business_id, app_id, path_name, group)
            return

        # Check if it's order is greater than the last report
        if order_of_chart > self._tabs_last_order[tabs_group_entry]:
            self._tabs_last_order[tabs_group_entry] = order_of_chart

        if not self._tabs[tabs_group_entry].get(tab):
            self._tabs[tabs_group_entry][tab] = [report_id]
            await self._update_tabs_group_metadata(business_id, app_id, path_name, group)
            return

        self._tabs[tabs_group_entry][tab] = self._tabs[tabs_group_entry][tab] + [report_id]
        await self._update_tabs_group_metadata(business_id, app_id, path_name, group)

    @logging_before_and_after(logging_level=logger.debug)
    async def _create_chart(
            self, data: Union[str, DataFrame, List[Dict]],
            menu_path: str, report_metadata: Dict,
            order: Optional[int] = None,
            rows_size: Optional[int] = None,
            cols_size: Optional[int] = None,
            padding: Optional[int] = None,
            overwrite: Optional[bool] = True,
            real_time: Optional[bool] = False,
            tabs_index: Optional[Tuple[str, str]] = None,
    ) -> str:
        """
        :param data:
        :param menu_path:
        :param report_metadata:
        :param overwrite: Whether to Update (delete) any report in
            the same menu_path and grid position or not
        """
        name, path_name = self._clean_menu_path(menu_path=menu_path)

        report_metadata: Dict = self._fill_report_metadata(
            report_metadata=report_metadata, path_name=path_name,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
        )

        app = await self._plot_aux.get_or_create_app_and_apptype(name=name)
        app_id: str = app['id']

        if overwrite:
            await self.async_delete(
                menu_path=menu_path,
                by_component_type=False,
                order=report_metadata.get('order'),
                grid=report_metadata.get('grid'),
                tabs_index=tabs_index,
                overwrite=True
            )

        report: Dict = await self._plot_aux.create_report(
            business_id=self.business_id,
            app_id=app_id,
            report_metadata=report_metadata,
            real_time=real_time,
        )
        report_id: str = report['id']
        self._report_order[report_id] = order

        if tabs_index:
            await self._insert_in_tab(self.business_id, app_id, path_name, report_id, tabs_index, order)

        try:
            if data:
                await self._plot_aux.update_report_data(
                    business_id=self.business_id,
                    app_id=app_id,
                    report_id=report_id,
                    report_data=data,
                )
        except ValueError:
            if not data.empty:
                await self._plot_aux.update_report_data(
                    business_id=self.business_id,
                    app_id=app_id,
                    report_id=report_id,
                    report_data=data,
                )

        return report_id

    @logging_before_and_after(logging_level=logger.debug)
    async def _create_trend_chart(
            self, echart_type: str,
            data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str],  # first layer
            menu_path: str,
            row: Optional[int] = None,  # TODO to deprecate
            column: Optional[int] = None,    # TODO to deprecate
            order: Optional[int] = None,
            rows_size: Optional[int] = None,
            cols_size: Optional[int] = None,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            overwrite: bool = True,
            report_metadata: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            aggregation_func: Optional[Callable] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ) -> str:
        """For Linechart, Barchart, Stocklinechart, Scatter chart, and alike

        Example
        -------------------
        input
            data:
                val_a, val_b,
                  mon,     7,
                  tue,     10,
                  wed,     11,
                  thu,     20,
                  fri,     27,
            x: 'val_a'
            y: 'val_b'
            menu_path: 'purchases/weekly'
            row: 2
            column: 1
            title: 'Purchases by week'
            color: None
            option_modifications: {}

        :param echart_type:
        :param data:
        :param x:
        :param y:
        :param menu_path: it contain the `app_name/path` for instance "product-suite/results"
            and it will use the AppType ProductSuite (if it does not it will create it)
            then it will check if the App exists, if not create it and finally create
            the report with the specific path "results"
        :param row:
        :param column:
        :param title:
        :param option_modifications:
        :param filters: To create a filter for every specified column
        """
        if isinstance(x, str):
            x: List[str] = [x]

        if isinstance(y, str):
            y: List[str] = [y]

        cols: List[str] = x + y

        self._plot_aux.validate_table_data(data, elements=cols)
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[cols]  # keep only x and y

        if any(df[x].duplicated()):

            if not aggregation_func:
                raise ValueError("There are duplicate entries in the data provided but the "
                                 "aggregation function has not been defined.")

            # Aggregate grouped object
            df = df.groupby(x).agg(aggregation_func).reset_index()

            # Multindexed columns in pandas is stored as a tuple, so we just need to join with a space to make it
            # one level indexed column
            if any(isinstance(elem, Tuple) for elem in df.columns):
                df.columns = [
                    " ".join(col) if len(col[1]) > 0 else col[0]
                    for col in df.columns
                ]

        #https://stackoverflow.com/questions/42099312/how-to-create-an-infinite-iterator-to-generate-an-incrementing-alphabet-pattern
        def __column_name_generator():
            for p in product(['x', 'y', 'z'], repeat=1):
                yield ''.join(p)

        df.rename(columns={x_col: letter+'Axis' for x_col, letter in zip(x, __column_name_generator())}, inplace=True)

        # Default
        option_modifications_temp = {"legend": {"type": "scroll"}}

        if option_modifications:
            if option_modifications.get('optionModifications'):
                option_modifications['optionModifications'].update(option_modifications_temp)
            else:
                option_modifications['optionModifications'] = option_modifications_temp
        else:
            option_modifications: Dict = {}
            option_modifications['optionModifications'] = option_modifications_temp

        # TODO we have two titles now, take a decision
        #  one in dataFields the other as field
        data_fields: Dict = self._set_data_fields(
            title='', subtitle=subtitle,
            x_axis_name=x_axis_name,
            y_axis_name=y_axis_name,
            option_modifications=option_modifications,
        )
        data_fields['type'] = echart_type

        if report_metadata:
            if not report_metadata.get('reportType'):
                report_metadata['reportType'] = 'ECHARTS'
            if not report_metadata.get('dataFields'):
                report_metadata['dataFields'] = data_fields
            if not report_metadata.get('title'):
                report_metadata['title'] = 'title'
        else:
            report_metadata: Dict = {
                'reportType': 'ECHARTS',
                'dataFields': data_fields,
                'title': title,
            }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        if filters:
            raise NotImplementedError

        return await self._create_chart(
            data=df,
            menu_path=menu_path, overwrite=overwrite,
            report_metadata=report_metadata, order=order,
            rows_size=rows_size, cols_size=cols_size, padding=padding,
            tabs_index=tabs_index,
        )

    @logging_before_and_after(logging_level=logger.debug)
    def _create_multifilter_reports(
            self, indices: List[str], values: List[str], data: Union[str, DataFrame, List[Dict]], filters: Dict
    ) -> Iterable:
        """
        Create chunks of the data to create N reports for every filter combination
        """
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        filter_cols: List[str] = filters['filter_cols']
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)[indices + filter_cols + values]

        select_filter: Dict[str, str] = {
            v: f'Select{index + 1}'
            for index, v in enumerate(filter_cols)
        }

        if "get_all" not in filters:
            filters["get_all"] = []
        elif isinstance(filters["get_all"], bool) and filters["get_all"]:
            filters["get_all"] = [filt_col for filt_col in filter_cols]

        # Create all combinations
        # https://stackoverflow.com/questions/18497604/combining-all-combinations-of-two-lists-into-a-dict-of-special-form
        d: Dict = {}
        uuid_str = uuid.uuid1()
        for filter_name in filter_cols:
            d[filter_name] = df[filter_name].unique().tolist()
            if len(d[filter_name]) > 1 and filter_name in filters["get_all"]:
                d[filter_name] += [uuid_str]

        filter_combinations = [
            dict(zip((list(d.keys())), row))
            for row in product(*list(d.values()))
        ]

        for filter_combination in filter_combinations:
            df_temp = df.copy()
            filter_element: Dict = {}
            for filter_, value in filter_combination.items():
                if value != uuid_str:
                    filter_element[select_filter[filter_]] = value
                    df_temp = df_temp[df_temp[filter_] == value]
                else:
                    filter_element[select_filter[filter_]] = "All"
                    df_temp[filter_] = "All"

                if df_temp.empty:
                    break

            # Get rid of NaN columns based on the filters
            drop_cols = [col for col in df_temp.columns if df_temp[col].count() == 0]
            df_temp = df_temp.drop(drop_cols, axis=1).fillna(0)

            if df_temp.empty:
                continue

            yield df_temp, filter_element

    @logging_before_and_after(logging_level=logger.debug)
    async def _update_filter_report(
            self, filter_row: Optional[int],
            filter_column: Optional[int],
            filter_order: Optional[int],
            filter_elements: List,
            menu_path: str,
            update_type: str = 'concat',
            tabs_index: Optional[Tuple[str, str]] = None,
    ) -> None:
        """"""
        filter_reports: List[Dict] = (
            await self._find_target_reports(
                menu_path=menu_path,
                grid=f'{filter_row}, {filter_column}',
                order=filter_order,
                component_type='MULTIFILTER',
                by_component_type=True,
            )
        )

        try:
            assert len(filter_reports) == 1
            filter_report = filter_reports[0]
        except AssertionError:
            raise ValueError(
                f'The Filter you are defining does not exist in the specified position | '
                f'{len(filter_reports)} | row {filter_row} | column {filter_column}'
            )

        filter_report_data: Dict = json.loads(
            filter_report['chartData']
        )

        # Here we append old and new reportId
        df_filter_report_data: pd.DataFrame = pd.DataFrame(filter_report_data)
        df_filter_elements: pd.DataFrame = pd.DataFrame(filter_elements)

        if update_type == 'concat':
            df_chart_data: pd.DataFrame = pd.concat([
                df_filter_report_data,
                df_filter_elements,
            ])
        elif update_type == 'append':
            df_chart_data: pd.DataFrame = pd.merge(
                df_filter_report_data, df_filter_elements,
                how='left', on=[
                    c
                    for c in df_filter_report_data.columns
                    if 'Select' in c
                ], suffixes=('_old', '_new')
            )
            df_chart_data['reportId'] = (
                df_chart_data['reportId_old']
                +
                df_chart_data['reportId_new']
            )
            df_chart_data.drop(
                columns=['reportId_old', 'reportId_new'],
                axis=1, inplace=True,
            )
        else:
            raise ValueError(
                f'update_type can only be "concat" or "append" | '
                f'Value provided is {update_type}'
            )

        chart_data: List[Dict] = df_chart_data.to_dict(orient='records')
        del df_chart_data

        report_metadata: Dict = {
            'reportType': 'MULTIFILTER',
            'grid': f'{filter_row}, {filter_column}',
            'title': '',
        }

        await self._create_chart(
            data=chart_data,
            menu_path=menu_path,
            report_metadata=report_metadata,
            overwrite=True,
            tabs_index=tabs_index,
        )

    @logging_before_and_after(logging_level=logger.debug)
    async def _create_trend_charts_with_filters(
            self, data: Union[str, DataFrame, List[Dict]],
            filters: Dict, **kwargs,
    ):
        """"""
        filter_elements: List[Dict] = []
        self._validate_filters(filters=filters)
        x = kwargs['x']
        y = kwargs['y']
        if isinstance(x, str):
            x = [x]
        if isinstance(y, str):
            y = [y]
        tabs_index = kwargs.get("tabs_index")

        multifilter_tasks = []
        first_overwrite = True
        # We are going to save all the reports one by one
        for df_temp, filter_element in (
                self._create_multifilter_reports(
                    indices=x, values=y, data=data, filters=filters,
                )
        ):
            kwargs_: Dict = kwargs.copy()
            cols: List[str] = df_temp.columns.to_list()

            kwargs_['y'] = [
                value for value in cols
                if value not in x + filters["filter_cols"]
            ]
            if len(kwargs_['y']) == 0:
                continue

            if not kwargs_['aggregation_func']:
                kwargs_['aggregation_func'] = np.sum

            if first_overwrite:
                report_id = await self._create_trend_chart(data=df_temp, overwrite=True, **kwargs_)
                filter_element['reportId'] = [report_id]
            else:
                multifilter_tasks += [self._create_trend_chart(data=df_temp, overwrite=False, **kwargs_)]

            filter_elements.append(filter_element)
            first_overwrite = False     # Just overwrite once to delete previous plots

        report_ids = await asyncio.gather(*multifilter_tasks)
        for i in range(1, len(filter_elements)):
            filter_elements[i]['reportId'] = [report_ids[i-1]]

        update_filter_type: Optional[str] = filters.get('update_filter_type')
        filter_row: Optional[int] = filters.get('row')
        filter_column: Optional[int] = filters.get('column')
        filter_order: Optional[int] = filters.get('order')

        if update_filter_type:
            # concat is to add new filter options
            # append is to add new reports to existing filter options
            try:
                assert update_filter_type in ['concat', 'append']
            except AssertionError:
                raise ValueError(
                    f'update_filter_type must be one of both: "concat" or "append" | '
                    f'Value provided: {update_filter_type}'
                )
            await self._update_filter_report(
                filter_row=filter_row,
                filter_column=filter_column,
                filter_order=filter_order,
                filter_elements=filter_elements,
                menu_path=kwargs['menu_path'],
                update_type=update_filter_type,
                tabs_index=tabs_index,
            )
        else:
            report_metadata: Dict = {
                'reportType': 'MULTIFILTER',
                'title': '',
            }

            if filter_row and filter_column:
                report_metadata['grid'] = f'{filter_row}, {filter_column}'
            elif filter_order is not None:
                report_metadata['order'] = filter_order
            else:
                raise ValueError('Either row and column or order must be provided')

            await self._create_chart(
                data=filter_elements,
                menu_path=kwargs['menu_path'],
                report_metadata=report_metadata,
                order=filter_order,
                overwrite=True,
                tabs_index=tabs_index,
            )

    @logging_before_and_after(logging_level=logger.debug)
    async def _create_trend_charts(
            self, data: Union[str, DataFrame, List[Dict]],
            filters: Optional[Dict], **kwargs,
    ):
        """
        Example
        -----------------
        filters: Dict = {
            'exists': False,
            'row': 1, 'column': 1,
            'filter_cols': [
                'seccion', 'frecuencia', 'region',
            ],
        }
        """
        if filters:
            await self._create_trend_charts_with_filters(
                data=data, filters=filters, **kwargs
            )
        else:
            await self._create_trend_chart(data=data, **kwargs)

    @logging_before_and_after(logging_level=logger.debug)
    def _set_data_fields(
            self, title: str, subtitle: str,
            x_axis_name: str, y_axis_name: str,
            option_modifications: Dict,
    ) -> Dict:
        """"""
        chart_options: Dict = {
            'title': title if title else "",
            'subtitle': subtitle if subtitle else "",
            'legend': True,
            'tooltip': True,
            'axisPointer': True,
            'toolbox': {
                'saveAsImage': True,
                'restore': True,
                'dataView': False,
                'dataZoom': True,
                'magicType': False,
            },
            'xAxis': {
                'name': x_axis_name if x_axis_name else "",
                'type': 'category',
            },
            'yAxis': {
                'name': y_axis_name if y_axis_name else "",
                'type': 'value',
            },
        }

        data_fields: Dict = {
            'chartOptions': chart_options,
        }

        if option_modifications:
            for k, v in option_modifications.items():
                if k == 'optionModifications':
                    data_fields[k] = v
                else:
                    data_fields['chartOptions'][k] = v

        return data_fields

    @logging_before_and_after(logging_level=logger.info)
    async def set_business(self, business_id: str):
        """"""
        # If the business id does not exists it raises an ApiClientError
        _ = await self._plot_aux.get_business(business_id)
        self._plot_aux.app_metadata_api.business_id = business_id
        self.business_id: str = business_id

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def set_new_business(self, name: str):
        """"""
        business: Dict = await self._plot_aux.create_business(name=name)
        self.business_id: str = business['id']

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def set_apps_orders(self, apps_order: Dict[str, int]) -> None:
        """
        :param apps_order: example {'test': 0, 'more-test': 1}
        """
        apps: List[Dict] = await self._plot_aux.get_business_apps(business_id=self.business_id)

        set_apps_tasks = []

        for app in apps:
            app_id: str = app['id']
            app_normalized_name_: str = app.get('normalizedName')
            app_name_: str = app.get('name')
            new_app_order: Union[str, int] = apps_order.get(app_normalized_name_)

            if new_app_order is None:  # try with the non normalized name too
                new_app_order: Union[str, int] = apps_order.get(app_name_)

            if new_app_order:
                set_apps_tasks += [
                    self._plot_aux.update_app(
                        business_id=self.business_id,
                        app_id=app_id,
                        app_metadata={'order': int(new_app_order)},
                    )
                ]
        await asyncio.gather(*set_apps_tasks)

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def set_sub_path_orders(self, paths_order: Dict[str, int]) -> None:
        """
        :param paths_order: example {
            'test/sub-path': 0,
            'test/sub-path-2': 1,
            'app2/sub-path-x': 0,
        }
        """
        for menu_path, order in paths_order.items():
            if '/' in menu_path:
                app_normalized_name, app_path_name = menu_path.split('/')
            else:
                app_normalized_name, app_path_name = menu_path, None

            if not app_path_name:
                raise ValueError('To order Apps use set_apps_order() instead!')

            app_normalized_name = self._plot_aux.create_normalized_name(app_normalized_name)
            app_path_name = self._plot_aux.create_normalized_name(app_path_name)

            app: Dict = await self._plot_aux.get_app_by_name(
                business_id=self.business_id,
                name=app_normalized_name,
            )
            app_id: str = app['id']

            reports: List[Dict] = await self._plot_aux.get_app_reports(
                business_id=self.business_id,
                app_id=app_id,
            )

            path_order_tasks = []

            for report in reports:
                original_path_name: str = report.get('path')
                if original_path_name:
                    path_name: str = self._plot_aux.create_normalized_name(original_path_name)
                    if path_name == app_path_name:
                        path_order_tasks.append(
                            self._plot_aux.update_report(
                                business_id=self.business_id,
                                app_id=app_id,
                                report_id=report['id'],
                                report_metadata={'pathOrder': int(order)},
                            )
                        )
            await asyncio.gather(*path_order_tasks)

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def get_input_forms(self, menu_path: str) -> List[Dict]:
        """"""
        target_reports: List[Dict] = (
            await self._find_target_reports(
                menu_path=menu_path,
                component_type='FORM',
            )
        )

        results: List[Dict] = []
        for report in target_reports:
            result: List = await self._plot_aux.get_report_dataset_data(
                business_id=self.business_id,
                app_id=report['appId'],
                report_id=report['id'],
            )

            clean_result: Dict = {}
            for element in result:
                clean_result['data'] = json.loads(element['customField1'])
                clean_result['order'] = report['order']
                clean_result['reportId'] = report['id']

            results = results + [clean_result]
        return results

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def append_data_to_trend_chart(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str],
            component_type: str,
            menu_path: str,
            row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None,
    ) -> None:
        """Append new data"""
        allowed_components_type: List[str] = [
            'line', 'bar', 'scatter', 'predictive_line',
        ]

        if component_type not in allowed_components_type:
            raise ValueError(
                f'{component_type} not allowed | '
                f'Must be one of {allowed_components_type}'
            )

        cols: List[str] = [x] + y
        self._plot_aux.validate_table_data(data, elements=cols)
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[cols]  # keep only x and y

        df.rename(columns={x: 'xAxis'}, inplace=True)

        if row and column:
            target_reports: List[Dict] = (
                await self._find_target_reports(
                    menu_path=menu_path, grid=f'{row}, {column}',
                    component_type=component_type,
                )
            )
        else:
            target_reports: List[Dict] = (
                await self._find_target_reports(
                    menu_path=menu_path, order=order,
                    component_type=component_type,
                )
            )

        # TODO for multifilter we will need to iterate on this
        assert len(target_reports) == 1

        for report in target_reports:
            await self._plot_aux.append_report_data(
                business_id=self.business_id,
                app_id=report['appId'],
                report_id=report['id'],
                report_data=df,
            )

    @logging_before_and_after(logging_level=logger.debug)
    async def _create_dataset_charts(
            self, menu_path: str, order: int,
            rows_size: int, cols_size: int,
            force_custom_field: bool = False,
            data: Optional[Union[str, DataFrame, List[Dict]]] = None,
            padding: Optional[str] = None,
            report_type: str = 'ECHARTS2',
            overwrite: bool = True,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            options: Optional[Dict] = None,
            report_dataset_properties: Optional[Dict] = None,
            sort: Optional[Dict] = None,
            real_time: bool = False,
    ) -> Dict[str, Union[Dict, List[Dict]]]:
        # TODO ojo debería no ser solo data tabular!!
        df: pd.DataFrame = self._plot_aux.validate_data_is_pandarable(data)

        report_metadata: Dict = {'reportType': report_type}

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        name, path_name = self._clean_menu_path(menu_path=menu_path)

        report_metadata: Dict = self._fill_report_metadata(
            report_metadata=report_metadata, path_name=path_name,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
        )

        app = await self._plot_aux.get_or_create_app_and_apptype(name=name)
        app_id: str = app['id']

        if overwrite:
            await self.async_delete(
                menu_path=menu_path,
                by_component_type=False,
                order=report_metadata.get('order'),
                grid=report_metadata.get('grid'),
                tabs_index=tabs_index,
                overwrite=True,
            )

        items: List[Dict] = self._plot_aux.transform_report_data_to_chart_data(report_data=df)

        if force_custom_field and len(items) == 1:  # 'FORM'
            items: Dict = self._plot_aux.convert_input_data_to_db_items(items[0])
        else:  # 'ECHARTS2'
            items: List[Dict[str]] = self._plot_aux.convert_input_data_to_db_items(items, sort)

        report_dataset = await self._plot_aux.create_report_and_dataset(
            business_id=self.business_id, app_id=app_id,
            report_metadata=report_metadata,
            items=items,
            report_properties=options,
            report_dataset_properties=report_dataset_properties,
            sort=sort,
            real_time=real_time,
        )
        report_id: str = report_dataset['report']['id']
        self._report_order[report_id] = report_dataset['report']['order']

        if tabs_index:
            await self._insert_in_tab(self.business_id, app_id, path_name, report_id, tabs_index, order)

        return report_dataset

    @logging_before_and_after(logging_level=logger.debug)
    async def async_delete(
            self, menu_path: str,
            tabs_index: Optional[str] = None,
            grid: Optional[str] = None,
            order: Optional[int] = None,
            row: Optional[int] = None,
            column: Optional[int] = None,
            component_type: Optional[str] = None,
            by_component_type: bool = True,
            overwrite: bool = False,
    ) -> None:
        """In cascade find the reports that match the query
        and delete them all
        """
        if grid:
            kwargs = {'grid': grid}
        elif order is not None:
            kwargs = {'order': order}
        elif row and column:
            kwargs = {'grid': f'{row}, {column}'}
        else:
            raise ValueError('Either Row and Column or Order must be specified')

        target_reports: List[Dict] = (
            await self._find_target_reports(
                menu_path=menu_path,
                component_type=component_type,
                by_component_type=by_component_type,
                tabs_index=tabs_index,
                **kwargs,
            )
        )

        business_reports = await self._plot_aux.get_business_reports(business_id=self.business_id)
        delete_report_tasks = []
        delete_app_tasks = []
        for report in target_reports:

            # Don't overwrite tabs
            if overwrite and report['reportType'] == 'TABS':
                continue

            report_id = report['id']
            app_id = report['appId']

            # Check if the report has been deleted by another task
            if report in business_reports:
                business_reports.remove(report)
            else:
                continue

            app_reports = [report for report in business_reports if report['appId'] == app_id]

            delete_report_tasks.append(
                self._plot_aux.delete_report(
                    business_id=self.business_id,
                    app_id=app_id,
                    report_id=report_id
                )
            )
            try:  # It should always exist
                del self._report_order[report_id]
            except KeyError:
                warnings.warn("Report wasn't correctly stored in self._report_order", RuntimeWarning)

            # Tabs data structures maintenance
            if report['reportType'] == 'TABS':
                app_name, path_name = self._clean_menu_path(menu_path)
                if not path_name:
                    path_name = ""
                data_fields = json.loads(report['dataFields'].replace("'", '"'))
                group_name = data_fields['groupName']
                tabs_group_entry = (app_id, path_name, group_name)

                try:
                    child_report_ids = [report_id_in_tab
                                        for tabs_list in self._tabs[tabs_group_entry].values()
                                        for report_id_in_tab in tabs_list]
                except KeyError:
                    self._clear_or_create_all_local_state()
                    await self._get_business_state(self.business_id)
                    child_report_ids = [report_id_in_tab
                                        for tabs_list in self._tabs[tabs_group_entry].values()
                                        for report_id_in_tab in tabs_list]

                # Add linked reports to the deletion queue
                target_reports += [report for report in app_reports if report['id'] in child_report_ids]
                if tabs_group_entry in self._tabs:
                    self._delete_tabs_group(tabs_group_entry)

            if self._report_in_tab.get(report_id):
                self._delete_report_id_from_tab(report_id)

            # Check if app can be deleted
            if not overwrite and len(app_reports) == 0:
                delete_app_tasks.append(
                    self._plot_aux.delete_app(
                        business_id=self.business_id,
                        app_id=app_id,
                    )
                )
        await asyncio.gather(*delete_report_tasks)
        await asyncio.gather(*delete_app_tasks)

    @async_auto_call_manager(execute=True)
    async def delete(
            self, menu_path: str,
            tabs_index: Optional[str] = None,
            grid: Optional[str] = None,
            order: Optional[int] = None,
            row: Optional[int] = None,
            column: Optional[int] = None,
            component_type: Optional[str] = None,
            by_component_type: bool = True,
            overwrite: bool = False,
    ):
        await self.async_delete(
                menu_path=menu_path, tabs_index=tabs_index, grid=grid, order=order, row=row,
                column=column, component_type=component_type, by_component_type=by_component_type,
                overwrite=overwrite
            )

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def delete_path(self, menu_path: str) -> None:
        """In cascade delete an App or Path and all the reports within it

        If menu_path contains an "{App}/{Path}" then it removes the path
        otherwise it removes the whole app
        """
        name, path_name = self._clean_menu_path(menu_path=menu_path)
        app: Dict = await self._plot_aux.get_app_by_name(
            business_id=self.business_id,
            name=name,
        )
        if not app:
            return

        app_id: str = app['id']
        if '/' not in menu_path:
            await self._plot_aux.delete_app(
                business_id=self.business_id,
                app_id=app_id,
            )
            self._clear_or_create_all_local_state()
            await self._get_business_state(self.business_id)
            return

        reports: List[Dict] = await self._plot_aux.get_app_reports(
            business_id=self.business_id, app_id=app_id,
        )

        if path_name:
            target_reports: List[Dict] = [
                report
                for report in reports
                if report['path'] == path_name
            ]
        else:
            target_reports: List[Dict] = reports

        delete_tasks = []
        for report in target_reports:
            report_id = report['id']
            delete_tasks.append(
                self._plot_aux.delete_report(
                    business_id=self.business_id,
                    app_id=app_id,
                    report_id=report_id
                )
            )
            del self._report_order[report_id]

            # Tabs data structures maintenance
            if report['reportType'] == 'TABS':
                path_name = report['path'] if report['path'] else ""
                data_fields = json.loads(report['dataFields'].replace("'", '"'))
                group_name = data_fields['groupName']
                tabs_group_entry = (app_id, path_name, group_name)
                if tabs_group_entry in self._tabs:
                    self._delete_tabs_group(tabs_group_entry)

            if self._report_in_tab.get(report_id):
                self._delete_report_id_from_tab(report_id)

        await asyncio.gather(*delete_tasks)

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def clear_business(self):
        """Calls "delete_path" for all the apps of the actual business, clearing the business"""
        tasks = [self._plot_aux.delete_app(business_id=self.business_id, app_id=app['id'])
                 for app in await self._plot_aux.get_business_apps(self.business_id)]

        await asyncio.gather(*tasks)
        self._clear_or_create_all_local_state()

    # TODO pending add append_report_data to free Echarts
    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def free_echarts(
            self, menu_path: str,
            data: Optional[Union[str, DataFrame, List[Dict]]] = None,
            options: Optional[Dict] = None,
            raw_options: Optional[Dict] = None,
            sort: Optional[Dict] = None,
            order: Optional[int] = None,
            rows_size: Optional[int] = None,
            cols_size: int = 12,
            padding: Optional[str] = None,
            overwrite: bool = True,
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            real_time: bool = False,
    ):
        """
        Example
        -------------
        sort = {
            'field': 'date'
            'direction': 'asc',
        }

        :param data:
        :param options: eCharts options of the type {'options': options}
        :param raw_options: eCharts copy paste options of the type {'options': options}
        :param menu_path:
        :param sort:
        :param order:
        :param rows_size:
        :param cols_size:
        :param padding:
        :param overwrite:
        :param filters:
        :param tabs_index:
        :param bentobox_data:
        :param real_time:
        """

        def transform_dict_js_to_py(options_str: str):
            """https://discuss.dizzycoding.com/how-to-convert-raw-javascript-object-to-python-dictionary/"""
            options_str = options_str.replace('\n', '')
            options_str = options_str.replace(';', '')
            return json5.loads(options_str)

        def retrieve_data_from_options(options_: Dict) -> Union[Dict, List]:
            """Retrieve data from eCharts options

            Example
            -----------
            input options = {'title': {'text': 'Stacked Area Chart'},
                 'tooltip': {'trigger': 'axis',
                  'axisPointer': {'type': 'cross', 'label': {'backgroundColor': '#6a7985'}}},
                 'legend': {'data': ['Email',
                   'Union Ads',
                   'Video Ads',
                   'Direct',
                   'Search Engine']},
                 'toolbox': {'feature': {'saveAsImage': {}}},
                 'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                 'xAxis': [{'type': 'category',
                   'boundaryGap': False,
                   'data': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']}],
                 'yAxis': [{'type': 'value'}],
                 'series': [{'name': 'Email',
                   'type': 'line',
                   'stack': 'Total',
                   'areaStyle': {},
                   'emphasis': {'focus': 'series'},
                   'data': [120, 132, 101, 134, 90, 230, 210]},
                  {'name': 'Union Ads',
                   'type': 'line',
                   'stack': 'Total',
                   'areaStyle': {},
                   'emphasis': {'focus': 'series'},
                   'data': [220, 182, 191, 234, 290, 330, 310]},
                  {'name': 'Video Ads',
                   'type': 'line',
                   'stack': 'Total',
                   'areaStyle': {},
                   'emphasis': {'focus': 'series'},
                   'data': [150, 232, 201, 154, 190, 330, 410]},
                  {'name': 'Direct',
                   'type': 'line',
                   'stack': 'Total',
                   'areaStyle': {},
                   'emphasis': {'focus': 'series'},
                   'data': [320, 332, 301, 334, 390, 330, 320]},
                  {'name': 'Search Engine',
                   'type': 'line',
                   'stack': 'Total',
                   'label': {'show': True, 'position': 'top'},
                   'areaStyle': {},
                   'emphasis': {'focus': 'series'},
                   'data': [820, 932, 901, 934, 1290, 1330, 1320]}]
                }

            output
                [{'Mon': 120,
                  'Tue': 132,
                  'Wed': 101,
                  'Thu': 134,
                  'Fri': 90,
                  'Sat': 230,
                  'Sun': 210},
                 {'Mon': 220,
                  'Tue': 182,
                  'Wed': 191,
                  'Thu': 234,
                  'Fri': 290,
                  'Sat': 330,
                  'Sun': 310},
                 {'Mon': 150,
                  'Tue': 232,
                  'Wed': 201,
                  'Thu': 154,
                  'Fri': 190,
                  'Sat': 330,
                  'Sun': 410},
                 {'Mon': 320,
                  'Tue': 332,
                  'Wed': 301,
                  'Thu': 334,
                  'Fri': 390,
                  'Sat': 330,
                  'Sun': 320},
                 {'Mon': 820,
                  'Tue': 932,
                  'Wed': 901,
                  'Thu': 934,
                  'Fri': 1290,
                  'Sat': 1330,
                  'Sun': 1320
                }
            ]
            """
            rows = []
            data = []
            cols = []
            if 'xAxis' in options:
                if type(options['xAxis']) == list:
                    if len(options['xAxis']) == 1:
                        if 'data' in options['xAxis'][0]:
                            rows = options['xAxis'][0]['data']
                elif type(options['xAxis']) == dict:
                    if 'data' in options['xAxis']:
                        rows = options['xAxis']['data']
                    elif type(options['xAxis']) == dict:
                        if 'data' in options['yAxis']:
                            rows = options['yAxis']['data']
                else:
                    raise ValueError('xAxis has multiple values only 1 allowed')
            elif 'radar' in options:
                if 'indicator' in options['radar']:
                    rows = [element['name'] for element in options['radar']['indicator']]
                elif type(options['radar']) == dict:
                    raise NotImplementedError('Multi-radar not implemented')

            if 'data' in options_:
                data = options_['data']
            if 'series' in options:
                if 'data' in options['series']:
                    pass
                else:
                    for serie in options['series']:
                        if 'data' in serie:
                            if serie.get('type') in ['pie', 'gauge']:
                                for datum in serie['data']:
                                    data.append(datum)
                            elif serie.get('type') == 'radar':
                                for datum in serie['data']:
                                    data.append(datum['value'])
                                    cols.append(datum['name'])
                                break
                            else:
                                data.append(serie['data'])

                        if 'name' in serie:
                            cols.append(serie['name'])
                        elif 'type' in serie:
                            cols.append(serie['type'])
            else:
                return {}

            df = pd.DataFrame(data)
            if not rows and not cols:
                return df.reset_index().to_dict(orient='records')
            if not rows:
                return df.to_dict(orient='records')

            if rows:
                df.columns = rows
            df_ = df.T
            df_.columns = cols
            return df_.reset_index().to_dict(orient='records')

        async def _create_free_echarts(
                _data: Union[str, DataFrame, List[Dict]],
                sort: Optional[Dict] = None,
        ) -> Dict[str, Union[Dict, List[Dict]]]:
            if filters:
                raise NotImplementedError

            return await self._create_dataset_charts(
                options=options,
                report_type='ECHARTS2',
                menu_path=menu_path, order=order,
                rows_size=rows_size, cols_size=cols_size, padding=padding,
                data=_data, bentobox_data=bentobox_data,
                force_custom_field=False, sort=sort,
                tabs_index=tabs_index
            )

        # TODO many things in common with _create_trend_charts_with_filters() unify!!
        async def _create_free_echarts_with_filters():
            """"""
            filter_elements: List[Dict] = []
            self._validate_filters(filters=filters)

            # We are going to save all the reports one by one
            for df_temp, filter_element in (
                    self._create_multifilter_reports(
                        data=data, filters=filters,
                    )
            ):
                report_id = _create_free_echarts(_data=df_temp)
                filter_element['reportId'] = [report_id]
                filter_elements.append(filter_element)

            update_filter_type: Optional[str] = filters.get('update_filter_type')
            filter_row: Optional[int] = filters.get('row')
            filter_column: Optional[int] = filters.get('column')
            filter_order: Optional[int] = filters.get('order')

            if update_filter_type:
                # concat is to add new filter options
                # append is to add new reports to existing filter options
                try:
                    assert update_filter_type in ['concat', 'append']
                except AssertionError:
                    raise ValueError(
                        f'update_filter_type must be one of both: "concat" or "append" | '
                        f'Value provided: {update_filter_type}'
                    )
                await self._update_filter_report(
                    filter_row=filter_row,
                    filter_column=filter_column,
                    filter_order=filter_order,
                    filter_elements=filter_elements,
                    menu_path=kwargs['menu_path'],
                    update_type=update_filter_type,
                )
            else:
                report_metadata: Dict = {
                    'reportType': 'MULTIFILTER',
                    'title': '',
                }

                if filter_row and filter_column:
                    report_metadata['grid'] = f'{filter_row}, {filter_column}'
                elif filter_order is not None:
                    report_metadata['order'] = filter_order
                else:
                    raise ValueError('Either row and column or order must be provided')

                await self._create_chart(
                    data=filter_elements,
                    menu_path=menu_path,
                    report_metadata=report_metadata,
                    order=filter_order,
                    overwrite=True,
                    tabs_index=tabs_index,
                )

        if options is None:
            if raw_options is None:
                raise ValueError('Either "options" or "raw_options" must be provided')
            else:
                options = transform_dict_js_to_py(raw_options)
                data = retrieve_data_from_options(options)
        elif data is None:
            raise ValueError('If "options" is provided "data" must be provided too')

        if filters:
            await _create_free_echarts_with_filters()
        else:
            await _create_free_echarts(data, sort=sort)


class PlotApi(BasePlot):
    """
    """

    @logging_before_and_after(logging_level=logger.debug)
    def __init__(self, api_client, app_metadata_api, **kwargs):
        super().__init__(api_client, app_metadata_api=app_metadata_api)
        if kwargs.get('business_id'):
            self.business_id: Optional[str] = kwargs['business_id']
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We are in a jupyter notebook, so we need to execute in a different loop
                jobs = bg.BackgroundJobManager()
                job = jobs.new(asyncio.run, self._get_business_state(self.business_id))
                while not job.finished:
                    time.sleep(0.1)
            else:
                asyncio.run(self._get_business_state(self.business_id))
        else:
            self.business_id: Optional[str] = None

        self._default_toolbox_options = {
            'show': True,
            'orient': 'horizontal',
            'itemSize': 20,
            'itemGap': 24,
            'showTitle': True,
            'zlevel': 100,
            'bottom': "2%",
            'right': "5%",
            'feature': {
                'dataView': {
                    'title': 'Data',
                    'readOnly': False,
                    'icon': 'image://https://uploads-ssl.webflow.com/619f9fe98661d321dc3beec7/6398a555461a3684b16d544e_database.svg',
                    'emphasis': {
                        'iconStyle': {
                            'textBackgroundColor': 'var(--chart-C1)',
                            'textBorderRadius': [50, 50, 50, 50],
                            'textPadding': [8, 8, 8, 8],
                            'textFill': 'var(--color-white)'
                        }
                    },
                },
                'magicType': {
                    'type': ['line', 'bar'],
                    'title': {
                        'line': 'Switch to Line Chart',
                        'bar': 'Switch to Bar Chart',
                    },
                    'icon': {
                        'line': 'image://https://uploads-ssl.webflow.com/619f9fe98661d321dc3beec7/6398a55564d52c1ba4d9884d_linechart.svg',
                        'bar': 'image://https://uploads-ssl.webflow.com/619f9fe98661d321dc3beec7/6398a5553cc6580f8e0edea4_barchart.svg'
                    },
                    'emphasis': {
                        'iconStyle': {
                            'textBackgroundColor': 'var(--chart-C1)',
                            'textBorderRadius': [50, 50, 50, 50],
                            'textPadding': [8, 8, 8, 8],
                            'textFill': 'var(--color-white)'
                        }
                    },
                },
                'saveAsImage': {
                    'show': True,
                    'title': 'Save as image',
                    'icon': 'image://https://uploads-ssl.webflow.com/619f9fe98661d321dc3beec7/6398a555662e1af339154c64_download.svg',
                    'emphasis': {
                        'iconStyle': {
                            'textBackgroundColor': 'var(--chart-C1)',
                            'textBorderRadius': [50, 50, 50, 50],
                            'textPadding': [8, 8, 8, 8],
                            'textFill': 'var(--color-white)'
                        }
                    }
                }
            }
        }

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def set_business(self, business_id: str):
        await super().set_business(business_id)
        self._clear_or_create_all_local_state()
        await self._get_business_state(self.business_id)

    # TODO both of this functions are auxiliary, and don't make sense here, find a better place for them
    @staticmethod
    @logging_before_and_after(logging_level=logger.debug)
    def _calculate_percentages_from_list(numbers, round_digits_min):
        def max_precision():
            max_p = 0
            for n in numbers:
                str_n = str(n)
                if '.' in str_n:
                    n_precision = len(str_n.split('.')[1])
                    max_p = n_precision if n_precision > max_p else max_p
            return max(max_p, round_digits_min)

        if isinstance(numbers, list):
            numbers = np.array(numbers)

        perc = np.round(100 * numbers / np.sum(numbers), max_precision())
        round_max = 99.9
        while np.sum(perc) > 99.99:
            perc = np.round(round_max * numbers / np.sum(numbers), max_precision())
            round_max -= 0.1
        return perc

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def insert_tabs_group_in_tab(self, menu_path: str, parent_tab_index: Tuple[str, str], child_tabs_group: str,
                                       last_in_order: Optional[bool] = True):
        app_name, path_name = self._clean_menu_path(menu_path)
        if not path_name:
            path_name = ""
        app: Dict = await self._plot_aux.get_app_by_name(business_id=self.business_id, name=app_name)
        app_id = app['id']
        child_id = self._tabs_group_id[(app_id, path_name, child_tabs_group)]
        order = self._report_order[child_id]
        parent_tabs_group_entry = (app_id, path_name, parent_tab_index[0])
        if parent_tabs_group_entry not in self._tabs:
            await self._create_tabs_group(self.business_id, parent_tabs_group_entry)
        if last_in_order:
            order = self._tabs_last_order[parent_tabs_group_entry] + 1
            await self._update_tabs_group_metadata(self.business_id, app_id, path_name, child_tabs_group, order)
            self._report_order[child_id] = order

        await self._insert_in_tab(self.business_id, app_id, path_name, child_id, parent_tab_index, order)

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def update_tabs_group_metadata(
            self, group_name: str, menu_path: str, order: Optional[int] = None,
            cols_size: Optional[int] = None, bentobox_data: Optional[Dict] = None,
            padding: Optional[str] = None, rows_size: Optional[int] = None,
            just_labels: Optional[bool] = None, sticky: Optional[bool] = None
    ):
        app_name, path_name = self._clean_menu_path(menu_path)
        if not path_name:
            path_name = ""
        app: Dict = await self._plot_aux.get_app_by_name(business_id=self.business_id, name=app_name)
        app_id = app['id']
        await self._update_tabs_group_metadata(self.business_id, app_id, path_name, group_name, order, cols_size,
                                               bentobox_data, padding, rows_size, just_labels, sticky)

    @async_auto_call_manager(execute=True)
    @logging_before_and_after(logging_level=logger.info)
    async def change_tabs_group_internal_order(self, group_name: str, menu_path: str, tabs_list: List[str]):
        app_name, path_name = self._clean_menu_path(menu_path)
        if not path_name:
            path_name = ""
        app: Dict = await self._plot_aux.get_app_by_name(business_id=self.business_id, name=app_name)
        app_id = app['id']
        tabs_group_entry = (app_id, path_name, group_name)
        tabs_group_aux = {}
        tabs_group = self._tabs[tabs_group_entry]
        for tab_name in tabs_list:
            if tab_name in tabs_group_aux:
                warnings.warn('Repeated name in order list! Ignoring this element.', RuntimeWarning)
                continue
            tabs_group_aux[tab_name] = tabs_group[tab_name]

        assert(len(tabs_group) == len(tabs_group_aux))
        self._tabs[tabs_group_entry] = tabs_group_aux
        await self._update_tabs_group_metadata(self.business_id, app_id, path_name, group_name)

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def table(
            self, data: Union[str, DataFrame, List[Dict]],
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None,
            # TODO
            # rows_size keeps being ignored
            rows_size: Optional[int] = None, cols_size: int = 12,
            title: Optional[str] = None,  # second layer
            filter_columns: Optional[List[str]] = None,
            search_columns: Optional[List[str]] = None,
            sort_table_by_col: Optional[Dict[str, str]] = None,
            horizontal_scrolling: bool = False,
            overwrite: bool = True,
            label_columns: Optional[Dict[str, str]] = {},
            downloadable_to_csv: bool = True,
            value_suffixes: Optional[Dict[str, str]] = {},
            tabs_index: Optional[Tuple[str, str]] = None
    ):
        """
        {
            "Product": null,
            "Monetary importance": {
                "field": "stringField2",
                "filterBy": ["High", "Medium", "Low"]
                "defaultOrder": "asc",
            },
            "Purchase soon": {
                "field": "stringField3",
                "filterBy": ["Yes", "No"]
            },
            {
                "field": "stringField4",
                "type": "search",
            },
        }
        """

        def _calculate_table_extra_map() -> Dict[str, str]:
            """
            Example
            ----------------
            input
                filter_columns = ["Monetary importance"]
                sort_table_by_col = {'date': 'asc'}
                search_columns = ['name']

            output
                filters_map = {
                    'stringField1': 'Monetary importance',
                    'stringField2': 'date',
                    'stringField3': 'name',
                }
            """
            filters_map: Dict[str, str] = {}
            key_prefix_name: str = 'stringField'
            if sort_table_by_col:
                if filter_columns:
                    field_cols: List[str] = filter_columns + list(sort_table_by_col.keys())
                else:
                    field_cols: List[str] = list(sort_table_by_col.keys())
            else:
                field_cols: List[str] = filter_columns

            if search_columns:
                if field_cols:
                    field_cols = field_cols + search_columns
                else:
                    field_cols = search_columns

            if field_cols:
                for index, filter_column in enumerate(field_cols):
                    filters_map[filter_column] = f'{key_prefix_name}{index + 1}'
                return filters_map
            else:
                return {}

        def _calculate_table_filter_fields() -> Dict[str, List[str]]:
            """
            Example
            ----------------
            input
                df
                    x, y, Monetary importance,
                    1, 2,                high,
                    2, 2,                high,
                   10, 9,                 low,
                    2, 1,                high,
                    4, 6,              medium,

                filter_columns = ["Monetary importance"]

            output
                filter_fields = {
                    'Monetary importance': ['high', 'medium', 'low'],
                }
            """
            filter_fields_: Dict[str, List[str]] = {}
            if filter_columns:
                for filter_column in filter_columns:
                    values: List[str] = df[filter_column].unique().tolist()

                    try:
                        assert len(values) <= 20
                    except AssertionError:
                        raise ValueError(
                            f'At maximum a table may have 20 different values in a filter | '
                            f'You provided {len(values)} | '
                            f'You provided {values}'
                        )
                    filter_fields_[filter_column] = values
                return filter_fields_
            else:
                return {}

        def _calculate_table_data_fields(DF: DataFrame) -> Dict:
            """
            Example
            -------------
            input
                df
                    x, y, Monetary importance,   name,
                    1, 2,                high,   jose,
                    2, 2,                high,  laura,
                   10, 9,                 low, audrey,
                    2, 1,                high,    ana,
                    4, 6,              medium,  jorge,

                filters_map = {
                    'stringField1': 'Monetary importance',
                    'stringField2': 'name'
                }

                filter_fields = {
                    'Monetary importance': ['high', 'medium', 'low'],
                }

                search_columns = ['name']

            output
                {
                    "Product": null,
                    "Monetary importance": {
                        "field": "stringField1",
                        "filterBy": ["high", "medium", "low"]
                    },
                    "name": {
                        "field": "stringField2",
                        "type": "search",
                    }
                }
            """

            def check_correct_value(n):
                admitted_types = (int, float, str, dt.date, np.float32, np.float64, np.int32, np.int64)
                if not isinstance(n, admitted_types):
                    raise ValueError("Invalid type for table data, admitted types are: " + str(admitted_types))

            #TODO this method should use a more general method to interpret color
            def interpret_color_info(color_def: Union[List, str]) -> Union[str, Dict]:
                def RGB_to_hex(r: int, g: int, b: int) -> str:
                    def clamp(x: int) -> int:
                        return max(0, min(x, 255))

                    # from https://stackoverflow.com/questions/3380726/converting-an-rgb-color-tuple-to-a-hexidecimal-string
                    return "#{0:02x}{1:02x}{2:02x}".format(clamp(r), clamp(g), clamp(b))

                # from https://xkcd.com/color/rgb/
                color_defs = {"purple": "#7e1e9c",
                              "red": "#e50000",
                              "green": "#15b01a",
                              "blue": "#0343df",
                              "pink": "#ff81c0",
                              "brown": "#653700",
                              "orange": "#f97306",
                              "yellow": "#ffff14",
                              "gray": "#929591",
                              "violet": "#9a0eea",
                              "cyan": "#00ffff",
                              "black": "#000000"
                              }

                default_FE_colors = ['active', 'error', 'warning', 'caution', 'main', 'neutral']
                radius_options = ['rectangle', 'rounded']
                variant_options = ['filled', 'outlined']

                options = None
                if isinstance(color_def, tuple):
                    options_list = color_def[1:]
                    options = {}
                    color_def = color_def[0]

                    for option in options_list:
                        if option in radius_options:
                            options['radius'] = option
                        elif option in variant_options:
                            options['variant'] = option
                        else:
                            raise ValueError("Can't interpret style options information.")

                if isinstance(color_def, list):
                    color_def = RGB_to_hex(color_def[0], color_def[1], color_def[2])
                elif color_def in default_FE_colors:
                    pass
                elif color_def in color_defs:
                    color_def = color_defs[color_def]
                elif not isinstance(color_def, str) or '#' not in color_def:
                    raise ValueError("Can't interpret color information.")

                if options:
                    options['color'] = color_def
                    return options

                return color_def

            def interpret_label_info(_labels_map, _value_suffix):
                if isinstance(_labels_map, Dict):
                    labels_map_aux = _labels_map.copy()
                    _labels_map = {}
                    for value, color_def in labels_map_aux.items():
                        color_def = interpret_color_info(color_def)
                        if isinstance(value, tuple):
                            df_values = DF[DF[col].between(value[0], value[1])][col].unique()
                            for val in df_values:
                                check_correct_value(val)
                                if _value_suffix == "" and isinstance(val, float) and int(val) - val == 0:
                                    val = int(val)
                                _labels_map[f'{val}{_value_suffix}'] = color_def
                        else:
                            check_correct_value(value)
                            _labels_map[f'{value}{_value_suffix}'] = color_def

                elif isinstance(_labels_map, (str, list, tuple)):
                    if _labels_map != "true":
                        df_values = DF[col].unique()
                        color_def = interpret_color_info(_labels_map)
                        _labels_map = {}
                        for val in df_values:
                            check_correct_value(val)
                            if _value_suffix == "" and isinstance(val, float) and int(val) - val == 0:
                                val = int(val)
                            _labels_map[f'{val}{_value_suffix}'] = color_def

                else:
                    raise ValueError("Can't interpret label information")

                return _labels_map

            data_fields: Dict = {}
            cols: List[str] = df.columns.tolist()
            if sort_table_by_col:
                cols_to_sort_by: List[str] = list(sort_table_by_col.keys())
            else:
                cols_to_sort_by: List[str] = []

            for col in cols:
                if col in filter_fields:
                    data_fields[col] = {
                        'field': extra_map[col],
                        'filterBy': filter_fields[col],
                    }
                else:
                    data_fields[col] = None

                if col in cols_to_sort_by:
                    if data_fields:
                        if data_fields[col]:
                            data_fields[col].update(
                                {
                                    'field': extra_map[col],
                                    "defaultOrder": sort_table_by_col[col],
                                }
                            )
                        else:
                            data_fields[col] = {
                                'field': extra_map[col],
                                "defaultOrder": sort_table_by_col[col],
                            }
                    else:
                        data_fields[col] = {
                            'field': extra_map[col],
                            "defaultOrder": sort_table_by_col[col],
                        }

                if search_columns:
                    if col in search_columns:
                        if data_fields:
                            if data_fields[col]:
                                raise ValueError(
                                    f'Column {col} | '
                                    f'You cannot assign the same column '
                                    f'to "search_columns" and '
                                    f'"filter_columns" simultaneously'
                                )
                            else:
                                data_fields[col] = {
                                    'field': extra_map[col],
                                    "type": "search",
                                }
                        else:
                            data_fields[col] = {
                                'field': extra_map[col],
                                "type": "search",
                            }

                if col in label_columns:
                    value_suffix = ""
                    if col in value_suffixes:
                        value_suffix = value_suffixes[col]

                    labels_map = interpret_label_info(label_columns[col], value_suffix)

                    if not data_fields[col]:
                        data_fields[col] = {'isLabel': labels_map}
                    else:
                        data_fields[col]['isLabel'] = labels_map

            return json.dumps(data_fields)

        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)

        if sort_table_by_col:
            try:
                assert len(sort_table_by_col) == 1
            except AssertionError:
                raise ValueError(
                    f'Currently we can only sort tables by one column '
                    f'You passed {len(sort_table_by_col)} columns'
                )

        # This is for the responsive part of the application
        #  by default 6 is the maximum for average desktop screensize
        #  then it starts creating an horizontal scrolling
        if horizontal_scrolling:
            if len(df.columns) > 6:
                raise ValueError(
                    f'Tables with more than 6 columns are not allowed'
                )

        extra_map: Dict[str, str] = _calculate_table_extra_map()
        filter_fields: Dict[str, List[str]] = _calculate_table_filter_fields()

        name, path_name = self._clean_menu_path(menu_path=menu_path)
        # TODO investigate what to do with this
        # try:
        #     d: Dict[str, Dict] = await self._plot_aux.create_app_type_and_app(
        #         business_id=self.business_id,
        #         app_type_metadata={'name': name},
        #         app_metadata={},
        #     )
        #     app: Dict = d['app']
        # except ApiClientError:  # Business admin user
        app: Dict = await self._plot_aux.get_app_by_name(business_id=self.business_id, name=name)
        if not app:
            app: Dict = await self._plot_aux.create_app(
                business_id=self.business_id, name=name,
            )

        app_id: str = app['id']

        if not isinstance(downloadable_to_csv, bool):
            raise TypeError("The type of the parameter 'downloadable_to_csv' needs to be a boolean, the type of the"
                             " parameter provided is: " + str(type(downloadable_to_csv)))

        report_metadata: Dict[str, Any] = {
            'title': title,
            'path': path_name,
            'order': order,
            'dataFields': _calculate_table_data_fields(df),
            'sizeColumns': cols_size,
            'sizeRows': rows_size,
            'properties': '{"downloadable":' + str(downloadable_to_csv).lower() + '}'
        }

        for col, value_format in value_suffixes.items():
            df[col] = df[col].astype(str)+value_format

        if row and column:
            report_metadata['grid']: str = f'{row}, {column}'
            report_metadata['order']: int = 0

        if overwrite:
            if not row and not column and order is None:
                raise ValueError(
                    'Row, Column or Order must be specified to overwrite a report'
                )

            if report_metadata.get('grid'):
                await self.async_delete(
                    menu_path=menu_path,
                    grid=report_metadata.get('grid'),
                    by_component_type=False,
                    tabs_index=tabs_index,
                    overwrite=overwrite,
                )
            else:
                await self.async_delete(
                    menu_path=menu_path,
                    order=order,
                    by_component_type=False,
                    tabs_index=tabs_index,
                    overwrite=overwrite,
                )

        report: Dict = await self._plot_aux.create_report(
            business_id=self.business_id,
            app_id=app_id,
            report_metadata=report_metadata,
        )
        report_id: str = report['id']
        self._report_order[report_id] = order

        if tabs_index:
            await self._insert_in_tab(self.business_id, app_id, path_name, report_id, tabs_index, order)

        report_entry_filter_fields: Dict[str, List[str]] = {
            extra_map[extra_name]: values
            for extra_name, values in filter_fields.items()
        }

        # We do not allow NaN values for report Entry
        df = df.fillna('')
        report_entries: List[Dict] = (
            self._plot_aux.convert_dataframe_to_report_entry(
                df=df, sorting_columns_map=extra_map,
            )
        )

        await self._plot_aux.update_report_data(
            business_id=self.business_id,
            app_id=app_id,
            report_id=report_id,
            report_data=report_entries,
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def html(
            self, html: str, menu_path: str,
            title: Optional[str] = None,
            row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        report_metadata: Dict = {
            'reportType': 'HTML',
            'order': order if order else 1,
            'title': title if title else '',
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=[{'value': html}],
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def iframe(
            self, menu_path: str, url: str,
            row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,
            height: Optional[int] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        report_metadata: Dict = {
            'reportType': 'IFRAME',
            'dataFields': {
                'url': url,
                'height': height if height else 600
            },
            'order': order if order else 1,
            'title': title if title else '',
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=[],
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def bar(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str],  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """Create a barchart
        """

        # TODO this only works for single bar:
        """
        'xAxis': {
            'axisLabel': {
                'inside': True,
                'color': '#ffffff'
            },
            'axisTick': {
                'show': False
            }
        },
        'color': '#002FD8',  # put multicolor
        """

        if not option_modifications:
            option_modifications = {
                'subtitle': subtitle if subtitle else '',
                'legend': True,
                'tooltip': True,
                'axisPointer': True,
                'toolbox': {
                    'saveAsImage': True,
                    'restore': True,
                    'dataView': True,
                    'dataZoom': True,
                    'magicType': True,
                },
                'xAxis': {
                    'name': x_axis_name if x_axis_name else "",
                    'type': 'category',
                },
                'yAxis': {
                    'name': y_axis_name if y_axis_name else "",
                    'type': 'value',
                },
                'optionModifications': {
                    'yAxis': {"axisLabel": {"margin": 12}, 'nameGap': 24},
                    'series': {
                        'smooth': True,
                        'itemStyle': {'borderRadius': [9, 9, 0, 0]}
                    },
                }
                # 'dataZoom': True,
            }

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=y,
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='bar',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def horizontal_barchart(
            self, data: Union[str, DataFrame, List[Dict]],
            x: List[str], y: str,  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """Create a Horizontal barchart
        https://echarts.apache.org/examples/en/editor.html?c=bar-y-category
        """
        option_modifications: Dict[str, Any] = {
            'dataZoom': False,
            'subtitle': subtitle if subtitle else '',
            'legend': True,
            'tooltip': True,
            'axisPointer': True,
            'toolbox': {
                'saveAsImage': True,
                'restore': True,
                'dataView': True,
                'dataZoom': True,
                'magicType': True,
            },
            'xAxis': {
                'name': x_axis_name if x_axis_name else "",
                'type': 'value',
            },
            'yAxis': {
                'name': y_axis_name if y_axis_name else "",
                'type': 'category',
            },
            'optionModifications': {
                'yAxis': {'boundaryGap': True, "axisLabel": {"margin": 12}, 'nameGap': 24},
                'xAxis': {'boundaryGap': True, "axisLabel": {"margin": 12}, 'nameGap': 24},
                'series': {
                    'smooth': True,
                    'itemStyle': {'borderRadius': [0, 9, 9, 0]}
                },
            },
        }

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=y,
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='bar',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func,
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def zero_centered_barchart(
            self, data: Union[str, DataFrame, List[Dict]],
            x: List[str], y: str,  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """Create a Horizontal barchart
        https://echarts.apache.org/examples/en/editor.html?c=bar-y-category
        """
        option_modifications: Dict[str, Any] = {
            'dataZoom': False,
            'subtitle': subtitle if subtitle else '',
            'legend': True,
            'tooltip': True,
            'axisPointer': True,
            'toolbox': {
                'saveAsImage': True,
                'restore': True,
                'dataView': True,
                'dataZoom': True,
                'magicType': True,
            },
            'xAxis': {
                'name': x_axis_name if x_axis_name else "",
                'type': 'value',
                'position': 'top',
                'splitLine': {
                    'lineStyle': {'type': 'dashed'}
                }
            },
            'yAxis': {
                'name': y_axis_name if y_axis_name else "",
                'type': 'category',
                'axisLine': {'show': False},
                'axisLabel': {'show': False},
                'axisTick': {'show': False},
                'splitLine': {'show': False},
            },
            'optionModifications': {
                'yAxis': {'boundaryGap': True, "axisLabel": {"margin": 12}, 'nameGap': 24},
                'xAxis': {'boundaryGap': True, "axisLabel": {"margin": 12}, 'nameGap': 24},
            },
        }
        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=y,
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='bar',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func,
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def line(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str],  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # thid layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """"""
        if not option_modifications:
            option_modifications = {
                'subtitle': subtitle if subtitle else "",
                'legend': True,
                'tooltip': True,
                'axisPointer': True,
                'toolbox': {
                    'saveAsImage': True,
                    'restore': True,
                    'dataView': True,
                    'dataZoom': True,
                    'magicType': True,
                },
                'xAxis': {
                    'name': x_axis_name if x_axis_name else "",
                    'type': 'category',
                },
                'yAxis': {
                    'name': y_axis_name if y_axis_name else "",
                    'type': 'value',
                },
                'dataZoom': True,
                'optionModifications': {'series': {'smooth': True}}
            }
        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=y,
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='line',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def predictive_line(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str],  # first layer
            menu_path: str,
            min_value_mark: Any, max_value_mark: Any,
            color_mark: str = 'rgba(255, 173, 177, 0.4)',
            row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """
        :param data:
        :param x:
        :param y:
        :param menu_path:
        :param row:
        :param column:
        :param min_value_mark:
        :param max_value_mark:
        :param color_mark: RGBA code
        :param title:
        :param x_axis_name:
        :param y_axis_name:
        :param filters:
        """
        option_modifications = {
            'optionModifications': {
                'series': {
                    'smooth': True,
                    'markArea': {
                        'itemStyle': {
                            'color': color_mark
                        },
                        'data': [
                            [
                                {
                                    'name': 'Prediction',
                                    'xAxis': min_value_mark
                                },
                                {
                                    'xAxis': max_value_mark
                                }
                            ],
                        ],
                    }
                },
            }
        }

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=y,
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='line',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func,
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def line_with_confidence_area(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: str,  # above_band_name: str, below_band_name: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """
        https://echarts.apache.org/examples/en/editor.html?c=line-stack

        option = {
          title: {
            text: 'Stacked Line'
          },
          tooltip: {
            trigger: 'axis'
          },
          legend: {
            data: ['Email', 'Union Ads', 'Video Ads', 'Direct', 'Search Engine']
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
          },
          toolbox: {
            feature: {
              saveAsImage: {}
            }
          },
          xAxis: {
            type: 'category',
            boundaryGap: false,
            data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
          },
          yAxis: {
            type: 'value'
          },
          series: [
            {
              name: 'Email',
              type: 'line',
              stack: 'Total',
              data: [120, 132, 101, 134, 90, 230, 210]
            },
            {
              name: 'Union Ads',
              type: 'line',
              stack: 'Total',
              lineStyle: {
                opacity: 0
              },
              stack: 'confidence-band',
              symbol: 'none',
              data: [220, 182, 191, 234, 290, 330, 310]
            },
            {
              name: 'Video Ads',
              type: 'line',
              stack: 'Total',
              data: [150, 232, 201, 154, 190, 330, 410]
            },
            {
              name: 'Direct',
              type: 'line',
              data: [320, 332, 301, 334, 390, 330, 320]
            },
            {
              name: 'Search Engine',
              type: 'line',
              lineStyle: {
                opacity: 0
              },
              areaStyle: {
                color: '#ccc'
              },
              stack: 'confidence-band',
              symbol: 'none',
              data: [820, 932, 901, 934, 1290, 1330, 1320]
            }
          ]
        };

        """
        option_modifications = {
            'series': [{
                'smooth': True,
                'lineStyle': {
                    'opacity': 0
                },
                'areaStyle': {
                    'color': '#ccc'
                },
                'stack': 'confidence-band',
                'symbol': 'none',
            }, ],
        }

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=[y],
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='line',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func,
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def scatter_with_confidence_area(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: str,  # above_band_name: str, below_band_name: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """
        https://echarts.apache.org/examples/en/editor.html?c=line-stack

        option = {
          title: {
            text: 'Stacked Line'
          },
          tooltip: {
            trigger: 'axis'
          },
          legend: {
            data: ['Email', 'Union Ads', 'Video Ads', 'Direct', 'Search Engine']
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
          },
          toolbox: {
            feature: {
              saveAsImage: {}
            }
          },
          xAxis: {
            type: 'category',
            boundaryGap: false,
            data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
          },
          yAxis: {
            type: 'value'
          },
          series: [
            {
              name: 'Email',
              type: 'line',
              stack: 'Total',
              data: [120, 132, 101, 134, 90, 230, 210]
            },
            {
              name: 'Union Ads',
              type: 'line',
              stack: 'Total',
              lineStyle: {
                opacity: 0
              },
              stack: 'confidence-band',
              symbol: 'none',
              data: [220, 182, 191, 234, 290, 330, 310]
            },
            {
              name: 'Video Ads',
              type: 'line',
              stack: 'Total',
              data: [150, 232, 201, 154, 190, 330, 410]
            },
            {
              name: 'Direct',
              type: 'line',
              data: [320, 332, 301, 334, 390, 330, 320]
            },
            {
              name: 'Search Engine',
              type: 'line',
              lineStyle: {
                opacity: 0
              },
              areaStyle: {
                color: '#ccc'
              },
              stack: 'confidence-band',
              symbol: 'none',
              data: [820, 932, 901, 934, 1290, 1330, 1320]
            }
          ]
        };

        """
        option_modifications = {
            'series': [{
                'smooth': True,
                'lineStyle': {
                    'opacity': 0
                },
                'areaStyle': {
                    'color': '#ccc'
                },
                'stack': 'confidence-band',
                'symbol': 'none',
            }, ],
        }

        return await self._create_trend_chart(
            data=data, x=x, y=[y], menu_path=menu_path,
            row=row, column=column,
            title=title, subtitle=subtitle,
            x_axis_name=x_axis_name,
            y_axis_name=y_axis_name,
            option_modifications=option_modifications,
            echart_type='scatter',
            bentobox_data=bentobox_data,
            filters=filters,
            tabs_index=tabs_index,
            aggregation_func=aggregation_func
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def stockline(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str],  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """"""
        self._plot_aux.validate_table_data(data, elements=[x] + y)
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        data_fields: Dict = {
            "key": x,
            "labels": {
                "key": x_axis_name,
                "value": y_axis_name,
                "hideKey": False,
                "hideValue": False
            },
            "values": y,
            "dataZoomX": True,
            "smooth": True,
            "symbol": "circle",
        }

        report_metadata: Dict = {
            'reportType': 'STOCKLINECHART',
            'title': title if title else '',
            'dataFields': data_fields,
        }

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def scatter(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str],  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """"""
        try:
            assert 2 <= len(y) <= 3
        except Exception:
            raise ValueError(f'y provided has {len(y)} it has to have 2 or 3 dimensions')

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=y,
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='scatter',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func,
            )
        )

    @logging_before_and_after(logging_level=logger.info)
    async def bubble_chart(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str], z: str,  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,  # to create filters
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """
        self._create_trend_chart(
            data=data, x=x, y=y, menu_path=menu_path,
            row=row, column=column,
            title=title, subtitle=subtitle,
            x_axis_name=x_axis_name,
            y_axis_name=y_axis_name,
            option_modifications=option_modifications,
            echart_type='scatter',
            filters=filters,
        )
        """
        raise NotImplementedError

    @logging_before_and_after(logging_level=logger.info)
    def indicator(
            self, data: Union[str, DataFrame, List[Dict], Dict], value: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = 1, cols_size: int = 12,
            padding: Optional[str] = None,
            target_path: Optional[str] = None,
            header: Optional[str] = None,
            footer: Optional[str] = None,
            color: Optional[str] = None,
            align: Optional[str] = None,
            variant: Optional[str] = None,
            icon: Optional[str] = None,
            big_icon: Optional[str] = None,
            background_image: Optional[str] = None,
            vertical: Union[bool, str] = False,
            real_time: bool = False,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """
        :param data:
        :param value:
        :param menu_path:
        :param row:
        :param column:
        :param order:
        :param rows_size:
        :param cols_size:
        :param padding:
        :param target_path:
        :param header:
        :param footer:
        :param color:
        :param align: to align center, left or right a component
        :param real_time:
        :param bentobox_data:
        """

        @async_auto_call_manager()
        @logging_before_and_after(logging_level=logger.info)
        async def single_indicator(**kwargs):
            # Necessary for time logging and correct execution pool handling
            await self._create_chart(**kwargs)

        mandatory_elements: List[str] = [
            header, value
        ]
        mandatory_elements = [element for element in mandatory_elements if element]
        extra_elements: List[str] = [footer, color, align, variant, target_path, background_image, icon, big_icon]
        extra_elements = [element for element in extra_elements if element]

        self._plot_aux.validate_table_data(data, elements=mandatory_elements)
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[mandatory_elements + extra_elements]  # keep only x and y

        cols_to_rename: Dict[str, str] = {
            header: 'title',
            footer: 'description',
            value: 'value',
            color: 'color',
            align: 'align',
            variant: 'variant',
            background_image: 'backgroundImage',
            target_path: 'targetPath',
            icon: 'icon',
            big_icon: 'bigIcon'
        }

        cols_to_rename = {
            col_to_rename: v
            for col_to_rename, v in cols_to_rename.items()
            if col_to_rename in mandatory_elements + extra_elements
        }
        df.rename(columns=cols_to_rename, inplace=True)
        extra_elements = [cols_to_rename[x] if x in cols_to_rename else x
                          for x in extra_elements]

        for extra_element in extra_elements:
            if extra_element == 'align':
                df['align'] = df['align'].fillna('right')
            elif extra_element == 'color':
                df['color'] = df['color'].fillna('black')
            elif extra_element == 'variant':
                df['variant'] = df['variant'].fillna('default')
            elif extra_element in ('backgroundImage', 'description', 'targetPath', 'icon', 'bigIcon'):
                df[extra_element] = df[extra_element].fillna('')
            else:
                raise ValueError(f'{extra_element} is not solved')

        len_df = len(df)
        padding_right = None
        padding_left = None
        if vertical and (len_df > 1 or isinstance(vertical, str)):
            if bentobox_data:
                raise ValueError("The vertical configuration uses a bentobox so it cant be included in another bentobox")
            bentobox_data = {
                'bentoboxId': str(uuid.uuid1()),
                'bentoboxOrder': order,
                'bentoboxSizeColumns': cols_size,
                'bentoboxSizeRows': rows_size*len_df,
            }
            # fixexd cols_size for bentobox and variable rows size
            cols_size = 22
            rows_size *= 10

            padding = '1,1,0,1'
            if isinstance(vertical, str):
                html = (
                    f"<p>{vertical}</p>"
                )
                self.html(
                    html=html,
                    menu_path=menu_path,
                    order=order, rows_size=2, cols_size=cols_size,
                    bentobox_data=bentobox_data,
                    padding=padding,
                )
                order += 1

        else:
            cols_size = cols_size//len_df
            if cols_size < 2:
                raise ValueError(f'The calculation of the individual cols_size for each indicator '
                                 f'is too small (cols_size/len(df)): {cols_size}')

        last_index = df.index[-1]

        for index, df_row in df.iterrows():

            if index == last_index and vertical and (len_df > 1 or isinstance(vertical, str)):
                padding = '1,1,1,1'

            report_metadata: Dict = {
                'reportType': 'INDICATOR',
            }

            if bentobox_data:
                self._validate_bentobox(bentobox_data)
                report_metadata['bentobox'] = json.dumps(bentobox_data)

            if row and column:
                report_metadata['grid'] = f'{row}, {column}'

            report_metadata['properties'] = json.dumps(df_row.to_dict())

            single_indicator(
                data=[df_row.to_dict()],
                menu_path=menu_path,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                report_metadata=report_metadata,
                real_time=real_time,
                tabs_index=tabs_index,
            )

            if isinstance(order, int):
                order += 1

        return order

    @logging_before_and_after(logging_level=logger.info)
    def alert_indicator(
            self, data: Union[str, DataFrame, List[Dict]],
            value: str, target_path: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            header: Optional[str] = None,
            footer: Optional[str] = None,
            color: Optional[str] = None,
            vertical: Optional[bool] = False,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """"""
        elements: List[str] = [header, footer, value, color, target_path]
        elements = [element for element in elements if element]
        self._plot_aux.validate_table_data(data, elements=elements)
        return self.indicator(
            data=data, value=value,
            menu_path=menu_path, row=row, column=column,
            order=order, cols_size=cols_size, rows_size=rows_size, padding=padding,
            target_path=target_path,
            header=header,
            footer=footer, color=color,
            vertical=vertical,
            bentobox_data=bentobox_data,
            tabs_index=tabs_index
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def pie(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: str,  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """Create a Piechart
        """
        self._plot_aux.validate_table_data(data, elements=[x, y])
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[x, y]]  # keep only x and y
        df.rename(columns={x: 'name', y: 'value'}, inplace=True)

        if not option_modifications:
            option_modifications = {
                'legend': True,
                'tooltip': True,
                'toolbox': {
                    'saveAsImage': True,
                    'dataView': True,
                }
            }

        data_fields: Dict = {
            'type': 'pie',
            'chartOptions': option_modifications,
        }

        report_metadata: Dict = {
            'reportType': 'ECHARTS',
            'dataFields': data_fields,
            'title': title,
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if filters:
            raise NotImplementedError

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def radar(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: List[str],  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            # subtitle: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """Create a RADAR
        """
        self._plot_aux.validate_table_data(data, elements=[x] + y)
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[x] + y]  # keep only x and y
        df.rename(columns={x: 'name'}, inplace=True)
        data_fields: Dict = {
            'type': 'radar',
        }

        if option_modifications:
            data_fields['optionModifications'] = option_modifications

        report_metadata: Dict = {
            'reportType': 'ECHARTS',
            'dataFields': data_fields,
            'title': title,
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if filters:
            raise NotImplementedError

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @logging_before_and_after(logging_level=logger.info)
    @async_auto_call_manager()
    async def tree(
            self, data: Union[str, List[Dict]],
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """Create a Tree
        """
        self._plot_aux.validate_tree_data(data[0], vals=['name', 'value', 'children'])

        report_metadata: Dict = {
            'reportType': 'ECHARTS',
            'dataFields': {'type': 'tree'},
            'title': title,
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if filters:
            raise NotImplementedError

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def treemap(
            self, data: Union[str, List[Dict]],
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """Create a Treemap
        """
        self._plot_aux.validate_tree_data(data[0], vals=['name', 'value', 'children'])

        report_metadata: Dict = {
            'title': title,
            'reportType': 'ECHARTS',
            'dataFields': {'type': 'treemap'},
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if filters:
            raise NotImplementedError

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def sunburst(
            self, data: List[Dict],
            name: str, children: str, value: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """Create a Sunburst
        """
        self._plot_aux.validate_tree_data(data[0], vals=['name', 'children'])

        report_metadata: Dict = {
            'reportType': 'ECHARTS',
            'title': title,
            'dataFields': {'type': 'sunburst'},
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if filters:
            raise NotImplementedError

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def candlestick(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """"""
        y = ['open', 'close', 'highest', 'lowest']

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=y,
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='candlestick',
                tabs_index=tabs_index,
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def heatmap(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: str, value: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """"""
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[x, y, value]]  # keep only x and y
        df.rename(columns={x: 'xAxis', y: 'yAxis', value: 'value'}, inplace=True)

        option_modifications = {
            'subtitle': subtitle if subtitle else "",
            'toolbox': {
                'saveAsImage': True,
                'restore': True,
                'dataView': True,
                'dataZoom': True,
            },
            'xAxis': {
                'name': x_axis_name if x_axis_name else "",
                'type': 'category',
            },
            'yAxis': {
                'name': y_axis_name if y_axis_name else "",
                'type': 'category',
            },
            'visualMap': 'piecewise'
        }

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=[x, y], y=value,
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='heatmap',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func,
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def cohort(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: str, value: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            aggregation_func: Optional[Callable] = None,
    ):
        """"""
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[x, y, value]]  # keep only x and y
        df.rename(columns={x: 'xAxis', y: 'yAxis', value: 'value'}, inplace=True)

        option_modifications: Dict = {
            "toolbox": {"orient": "horizontal", "top": 0},
            "xAxis": {"axisLabel": {"margin": '10%'}},
            'optionModifications': {
                'grid': {
                    'bottom': '20%',
                    # 'top': '10%'
                },
                "visualMap": {
                    'calculable': True,
                    "inRange": {
                        "color": ['#cfb1ff', '#0000ff']
                    },
                },
            },
        }

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=x, y=[y, value],
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='heatmap',
                tabs_index=tabs_index,
                aggregation_func=aggregation_func
            )
        )


    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def predictive_cohort(self):
        """"""
        raise NotImplementedError

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def sankey(
            self, data: Union[str, DataFrame, List[Dict]],
            source: str, target: str, value: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """"""
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[source, target, value]]  # keep only x and y
        df.rename(
            columns={
                source: 'source',
                target: 'target',
                value: 'value',
            },
            inplace=True,
        )

        report_metadata: Dict = {
            'title': title,
            'reportType': 'ECHARTS',
            'dataFields': {'type': 'sankey'},
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if filters:
            raise NotImplementedError

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def funnel(
            self, data: Union[str, DataFrame, List[Dict]],
            name: str, value: str,
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """"""
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[name, value]]  # keep only x and y
        df.rename(
            columns={
                name: 'name',
                value: 'value',
            },
            inplace=True,
        )

        return await self._create_trend_charts(
            data=data, filters=filters,
            **dict(
                x=name, y=[value],
                menu_path=menu_path, row=row, column=column,
                order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
                title=title, subtitle=subtitle,
                x_axis_name=x_axis_name,
                y_axis_name=y_axis_name,
                option_modifications=option_modifications,
                bentobox_data=bentobox_data,
                echart_type='funnel',
                tabs_index=tabs_index,
            )
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def speed_gauge(
            self, data: Union[str, DataFrame, List[Dict]],
            name: str, value: str,
            menu_path: str,
            min: int, max: int,
            row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            # subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ) -> str:
        """
        option = {
          series: [
            {
              type: 'gauge',
              startAngle: 190,
              endAngle: -10,
              min: 0,
              max: 80,
              pointer: {
                show: true
              },
              progress: {
                show: true,
                overlap: false,
                roundCap: true,
                clip: false,
                itemStyle: {
                  borderWidth: 0,
                  borderColor: '#464646'
                }
              },
              axisLine: {
                lineStyle: {
                  width: 10
                }
              },
              splitLine: {
                show: true,
                distance: 0,
                length: 5
              },
              axisTick: {
                show: true
              },
              axisLabel: {
                show: true,
                distance: 30
              },
              data: gaugeData,
              title: {
                fontSize: 14,
                offsetCenter: ['0%', '30%'],
              },
              anchor: {
                show: true,
                showAbove: true,
                size: 25,
                itemStyle: {
                  borderWidth: 10
                }
              },
              detail: {
                bottom: 10,
                width: 10,
                height: 14,
                fontSize: 14,
                color: 'auto',
                borderRadius: 20,
                borderWidth: 0,
                formatter: '{value}%',
                offsetCenter: [0, '45%']
              }
            }
          ]
        }
        """
        self._plot_aux.validate_table_data(data, elements=[name, value])
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        title: str = (
            title if title
            else f'{df["name"].to_list()[0]}: {df["value"].to_list()[0]}'
        )
        df = df[[name, value]]  # keep only x and y
        df.rename(
            columns={
                name: 'name',
                value: 'value',
            },
            inplace=True,
        )

        data_fields: Dict = {
            'type': 'gauge',
            'optionModifications': {
                'series': {
                    'startAngle': 190,
                    'endAngle': -10,
                    'min': min,
                    'max': max,
                    'pointer': {
                        'show': True
                    },
                    'progress': {
                        'show': True,
                        'overlap': False,
                        'roundCap': True,
                        'clip': False,
                        'itemStyle': {
                            'borderWidth': 0,
                            'borderColor': '#464646'
                        }
                    },
                    'axisLine': {
                        'lineStyle': {
                            'width': 10
                        }
                    },
                    'splitLine': {
                        'show': True,
                        'distance': 0,
                        'length': 5
                    },
                    'axisTick': {
                        'show': True,
                    },
                    'axisLabel': {
                        'show': True,
                        'distance': 30
                    },
                    'title': {
                        'show': False,
                    },
                    'anchor': {
                        'show': True,
                        'showAbove': True,
                        'size': 25,
                        'itemStyle': {
                            'borderWidth': 10
                        }
                    },
                    'detail': {
                        'show': False,
                    }
                },
            },
        }

        if option_modifications:
            raise NotImplementedError

        report_metadata: Dict = {
            'reportType': 'ECHARTS',
            'dataFields': data_fields,
            'title': title,
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if filters:
            raise NotImplementedError

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def ring_gauge(
        self, data: Union[str, DataFrame, List[Dict]],
        name: str, value: str,
        menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
        order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
        padding: Optional[str] = None,
        title: Optional[str] = None,  # second layer
        # subtitle: Optional[str] = None,
        x_axis_name: Optional[str] = None,
        y_axis_name: Optional[str] = None,
        option_modifications: Optional[Dict] = None,  # third layer
        filters: Optional[Dict] = None,
        bentobox_data: Optional[Dict] = None,
        tabs_index: Optional[Tuple[str, str]] = None,
    ) -> str:
        """"""
        self._plot_aux.validate_table_data(data, elements=[name, value])
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[name, value]]  # keep only x and y
        df.rename(
            columns={
                name: 'name',
                value: 'value',
            },
            inplace=True,
        )

        data_fields: Dict = {
            'type': 'gauge',
        }
        if option_modifications:
            data_fields['optionModifications'] = option_modifications

        report_metadata: Dict = {
            'reportType': 'ECHARTS',
            'dataFields': data_fields,
            'title': title,
        }

        if bentobox_data:
            self._validate_bentobox(bentobox_data)
            report_metadata['bentobox'] = json.dumps(bentobox_data)

        if filters:
            raise NotImplementedError

        if row and column:
            report_metadata['grid'] = f'{row}, {column}'

        return await self._create_chart(
            data=data,
            menu_path=menu_path,
            order=order, rows_size=rows_size, cols_size=cols_size, padding=padding,
            report_metadata=report_metadata,
            tabs_index=tabs_index,
        )

    @logging_before_and_after(logging_level=logger.info)
    def doughnut(self,
        data: Union[str, List[Dict], pd.DataFrame],
        menu_path: str, order: int,
        name_field: Optional[str] = 'name', value_field: Optional[str] = 'value',
        rows_size: Optional[int] = 2, cols_size: int = 3,
        padding: Optional[str] = None,
        option_modifications: Optional[Dict] = None,  # third layer
        filters: Optional[Dict] = None,
        bentobox_data: Optional[Dict] = None,
        tabs_index: Optional[Tuple[str, str]] = None,
        rounded: Optional[bool] = True
    ):
        if not option_modifications:
            option_modifications = {
                'tooltip': {
                    'trigger': 'item',
                },
                'legend': {
                  'left': 'center'
                },
                'series':
                [
                    {
                        'type': 'pie',
                        'radius': ['40%', '70%'],
                        'avoidLabelOverlap': True,
                        'pointer': {
                            'show': False,
                        },
                        'itemStyle': {
                          'borderRadius': 10 if rounded else 0,
                        },
                        'label': {
                            'show': False,
                            'position': 'center'
                        },
                        'emphasis': {
                            'label': {
                                'show': True,
                                'fontSize': 30,
                                'fontWeight': 'bold',
                                'fontFamily': 'Rubik'
                            }
                        },
                        'labelLine': {
                          'show': False
                        },
                    }
                ]
            }

        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[name_field, value_field]].rename(columns={name_field: 'name', value_field: 'value'})

        if 'sort_values' not in df.columns:
            df['sort_values'] = range(len(df))
        return self.free_echarts(
            menu_path=menu_path,
            data=df,
            options=option_modifications,
            order=order,
            rows_size=rows_size,
            cols_size=cols_size,
            padding=padding,
            filters=filters,
            bentobox_data=bentobox_data,
            tabs_index=tabs_index,
            sort={
                'field': 'sort_values',
                'direction': 'asc',
            }
        )

    @logging_before_and_after(logging_level=logger.info)
    def rose(self,
        data: Union[str, List[Dict], pd.DataFrame],
        menu_path: str, order: int,
        name_field: Optional[str] = 'name', value_field: Optional[str] = 'value',
        rows_size: Optional[int] = 2, cols_size: int = 3,
        padding: Optional[str] = None,
        option_modifications: Optional[Dict] = None,  # third layer
        filters: Optional[Dict] = None,
        bentobox_data: Optional[Dict] = None,
        tabs_index: Optional[Tuple[str, str]] = None,
        rounded: Optional[bool] = True
    ):
        if not option_modifications:
            option_modifications = {
                'legend': {
                    'top': 'bottom'
                },
                'series':
                [
                    {
                        'name': 'Nightingale Chart',
                        'type': 'pie',
                        'radius': ['10%', '70%'],
                        'center': ['50%', '40%'],
                        'roseType': 'area',
                        'itemStyle': {
                          'borderRadius': 8 if rounded else 0,
                        },
                    }
                ]
            }

        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[name_field, value_field]].rename(columns={name_field: 'name', value_field: 'value'})

        if 'sort_values' not in df.columns:
            df['sort_values'] = range(len(df))
        return self.free_echarts(
            menu_path=menu_path,
            data=df,
            options=option_modifications,
            order=order,
            rows_size=rows_size,
            cols_size=cols_size,
            padding=padding,
            filters=filters,
            bentobox_data=bentobox_data,
            tabs_index=tabs_index,
            sort={
                'field': 'sort_values',
                'direction': 'asc',
            }
        )

    @logging_before_and_after(logging_level=logger.info)
    def shimoku_gauge(self,
        value: Union[int, float], menu_path: str, order: int,
        name: Optional[str] = None, color: Optional[Union[str, int]] = 1,
        rows_size: Optional[int] = 1, cols_size: int = 3,
        padding: Optional[str] = None,
        option_modifications: Optional[Dict] = None,  # third layer
        filters: Optional[Dict] = None,
        bentobox_data: Optional[Dict] = None,
        tabs_index: Optional[Tuple[str, str]] = None,
        is_percentage: bool = True,
    ):
        data = [{'value': abs(value)}]
        if name:
            data[0]['name'] = name

        #TODO this should use a more general method for interpreting color
        _default_FE_colors = ['success', 'error', 'warning', 'success-light',
                              'error-light', 'warning-light', 'status-error']
        if color in _default_FE_colors:
            color = f'var(--color-{color})'
        elif isinstance(color, int):
            color = f'var(--chart-C{abs(color)})'

        if not option_modifications:
            option_modifications = {
                'grid': {
                    'left': '5%',
                    'right': '5%',
                    'top': '5%',
                    'bottom': '5%',
                    'containLabel': True
                },
                'series': [
                    {
                        'type': 'gauge',
                        'startAngle': 180,
                        'endAngle': 0,
                        'radius': '100%',
                        'min': 0,
                        'max': 100,
                        'pointer': {
                            'show': False,
                        },
                        'progress': {
                            'show': True,
                            'width': 30 if rows_size > 1 else 25,
                            'overlap': False,
                            'roundCap': False,
                            'clip': False,
                            'itemStyle': {
                                'borderWidth': 0,
                                'borderColor': color,
                                'color': color,
                            }
                        },
                        'splitLine': {
                            'show': False,
                        },
                        'axisLine':
                            {'lineStyle':
                                 {'width': 30 if rows_size > 1 else 25}
                             },
                        'axisTick': {
                            'show': False
                        },
                        'axisLabel': {
                            'show': False,
                        },
                        'title': {
                            'fontSize': 16,
                            'fontFamily': 'Rubik',
                            'offsetCenter': ['0', '30'],
                        },
                        'data': data,
                        'detail': {
                            'fontSize': 24,
                            'fontFamily': 'Rubik',
                            'font': 'inherit',
                            'color': '#202A36',
                            'borderColor': 'auto',
                            'borderWidth': 0,
                            'formatter': ('-' if value < 0 else '') + '{value}' + ('%' if is_percentage else ''),
                            'valueAnimation': True,
                            'offsetCenter': ['0', '-10']
                        }
                    }
                ]
            }
        return self.free_echarts(
            menu_path=menu_path,
            data=data,
            options=option_modifications,
            order=order,
            rows_size=rows_size,
            cols_size=cols_size,
            padding=padding,
            filters=filters,
            bentobox_data=bentobox_data,
            tabs_index=tabs_index
        )

    @logging_before_and_after(logging_level=logger.info)
    def shimoku_gauges_group(
        self, gauges_data: Union[pd.DataFrame, List[Dict]], order: int, menu_path: str,
        rows_size: Optional[int] = None, cols_size: Optional[int] = 12,
        gauges_padding: Optional[str] = '3, 1, 1, 1',
        gauges_rows_size: Optional[int] = 11, gauges_cols_size: Optional[int] = 4,
        filters: Optional[Dict] = None, tabs_index: Optional[Tuple[str, str]] = None,
        calculate_percentages: Optional[bool] = False
    ):
        if isinstance(gauges_data, pd.DataFrame):
            gauges_data = gauges_data.to_dict(orient="records")

        if calculate_percentages:
            percentages = self._calculate_percentages_from_list([gauge['value'] for gauge in gauges_data], 0)
            for i in range(len(percentages)):
                gauges_data[i]['value'] = percentages[i]

        bentobox_data = {
            'bentoboxId': str(uuid.uuid1()),
            'bentoboxOrder': order,
            'bentoboxSizeColumns': cols_size,
            'bentoboxSizeRows': rows_size,
        }
        for gauge in gauges_data:
            order += 1
            self.shimoku_gauge(
                value=gauge['value'],
                menu_path=menu_path, order=order, name=gauge.get('name'),
                padding=gauge['padding'] if gauge.get('padding') else gauges_padding,
                color=gauge['color'] if gauge.get('color') else 1,
                rows_size=gauge['rows_size'] if gauge.get('rows_size') else gauges_rows_size,
                cols_size=gauge['cols_size'] if gauge.get('cols_size') else gauges_cols_size,
                bentobox_data=bentobox_data, tabs_index=tabs_index, filters=filters,
                is_percentage=gauge['is_percentage'] if gauge.get('is_percentage') else True,
            )
        return order+1

    @logging_before_and_after(logging_level=logger.info)
    def gauge_indicator(
            self, menu_path: str, order: int, value: int,
            title: Optional[str] = "", description: Optional[str] = "",
            cols_size: Optional[int] = 6, rows_size: Optional[int] = 1,
            color: Optional[Union[str, int]] = 1, tabs_index: Optional[Tuple[str, str]] = None
    ):
        bentobox_id = str(uuid.uuid1())
        bentobox_data = {
            'bentoboxId': bentobox_id,
            'bentoboxOrder': order,
            'bentoboxSizeColumns': cols_size,
            'bentoboxSizeRows': rows_size,
        }

        data_ = [
            {
                'description': description,
                'title': title,
                'value': '',
                'color': '',
                'align': 'left'
            }
        ]

        self.indicator(
            data=data_,
            menu_path=menu_path,
            order=order, rows_size=10, cols_size=17,
            padding='1, 1, 0, 1',
            value='value',
            color='color',
            header='title',
            footer='description',
            align='align',
            bentobox_data=bentobox_data,
            tabs_index=tabs_index,
        )

        data_gauge = [{'value': value}]

        #TODO this should use a more general method for interpreting color
        _default_FE_colors = ['success', 'error', 'warning', 'success-light',
                              'error-light', 'warning-light', 'status-error']
        if color in _default_FE_colors:
            color = f'var(--color-{color})'
        elif isinstance(color, int):
            color = f'var(--chart-C{abs(color)})'

        raw_options = {
            'grid': {
                'left': ['5%'],
                'right': ['5%'],
                'top': ['5%'],
                'bottom': ['5%'],
                'containLabel': True
            },
            'series': [
                {
                    'type': 'gauge',
                    'startAngle': 360,
                    'endAngle': 0,
                    'radius': '80%',
                    'center': ['50%', '40%'],
                    'min': 0,
                    'max': 100,
                    'pointer': {
                        'show': False,
                    },
                    'progress': {
                        'show': True,
                        'width': 20,
                        'overlap': False,
                        'roundCap': False,
                        'clip': False,
                        'itemStyle': {
                            'borderWidth': 0,
                            'color': color,
                        }
                    },
                    'splitLine': {
                        'show': False,
                    },
                    'axisLine': {'lineStyle': {'width': 20}},
                    'axisTick': {
                        'show': False
                    },
                    'axisLabel': {
                        'show': False,
                    },
                    'title': {
                        'show': False,
                        'fontSize': 16,
                        'fontFamily': 'Rubik',
                    },
                    'data': data_gauge,
                    'detail': {
                        'fontSize': 24,
                        'fontFamily': 'Rubik',
                        'font': 'inherit',
                        'color': 'var(--color-black)',
                        'borderColor': 'auto',
                        'borderWidth': 0,
                        'formatter': '{value}%',
                        'valueAnimation': True,
                        'offsetCenter': ['0', '60']
                    }
                }
            ]
        }

        self.free_echarts(
            data=data_gauge,
            options=raw_options,
            menu_path=menu_path,
            order=order+1, rows_size=10, cols_size=5,
            padding='2, 0, 1, 0',
            bentobox_data=bentobox_data,
            tabs_index=tabs_index
        )

    @logging_before_and_after(logging_level=logger.info)
    def themeriver(
            self, data: Union[str, DataFrame, List[Dict]],
            x: str, y: str, name: str,  # first layer
            menu_path: str, row: Optional[int] = None, column: Optional[int] = None,  # report creation
            order: Optional[int] = None, rows_size: Optional[int] = None, cols_size: int = 12,
            padding: Optional[str] = None,
            title: Optional[str] = None,  # second layer
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """
                df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        df = df[[x, y, name]]  # keep only x and y
        df.rename(
            columns={
                name: 'name',
                y: 'value',
            },
            inplace=True,
        )
        y = [y, name]
        self._create_trend_chart(
            data=df, x=x, y=y, menu_path=menu_path,
            row=row, column=column,
            title=title, subtitle=subtitle,
            x_axis_name=x_axis_name,
            y_axis_name=y_axis_name,
            option_modifications=option_modifications,
            echart_type='themeriver',
            filters=filters,
            tabs_index=tabs_index,
        )
        """
        raise NotImplementedError

    @logging_before_and_after(logging_level=logger.info)
    def stacked_barchart(
            self, data: Union[str, DataFrame, List[Dict]],
            menu_path: str,
            x: str,
            order: Optional[int] = None, rows_size: Optional[int] = 3, cols_size: int = 12,
            padding: Optional[str] = None,
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            show_values: Optional[List] = None,
            calculate_percentages: bool = False,
    ):
        """Create a stacked barchart
        """
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        value_columns = [col for col in df.columns if col != x]
        if calculate_percentages:
            df[value_columns] = df[value_columns].apply(
                lambda row: self._calculate_percentages_from_list(row, 2), axis=1)

        if not option_modifications:
            option_modifications = {
                'subtitle': subtitle if subtitle else '',
                'legend': {
                    'show': True,
                    'type': 'scroll',
                    'itemGap': 16,
                    'icon': 'circle'
                },
                'tooltip': {
                    'trigger': 'item',
                    'axisPointer': {'type': 'cross'},
                },
                'toolbox': self._default_toolbox_options,
                'xAxis': {
                    'type': 'category',
                    'fontFamily': 'Rubik',
                    'name': x_axis_name if x_axis_name else "",
                    'nameLocation': 'middle',
                    'nameGap': 35,
                },
                'yAxis': {
                    'name': y_axis_name if y_axis_name else "",
                    'type': 'value',
                    'fontFamily': 'Rubik',
                    'axisLabel': {
                        'formatter': '{value} %' if calculate_percentages else '{value}',
                    }
                },
                # 'dataZoom': True,
                'grid': {
                    'left': '2%',
                    'right': '2%',
                    'bottom': '10%',
                    'containLabel': True
                },
                'series': [{
                    'type': 'bar',
                    'stack': 'total',
                    'emphasis': {'focus': 'series'},
                    'label': {'show': not show_values or name in show_values},
                    'name': name,
                    'itemStyle': {'borderRadius': [0, 0, 0, 0] if name != value_columns[-1] else [8, 8, 0, 0]},
                } for name in value_columns],
            }

        if 'sort_values' not in df.columns:
            df['sort_values'] = range(len(df))
        return self.free_echarts(
            menu_path=menu_path,
            data=df,
            options=option_modifications,
            order=order,
            rows_size=rows_size,
            cols_size=cols_size,
            padding=padding,
            filters=filters,
            bentobox_data=bentobox_data,
            tabs_index=tabs_index,
            sort={
                'field': 'sort_values',
                'direction': 'asc',
            }
        )

    @logging_before_and_after(logging_level=logger.info)
    def stacked_horizontal_barchart(
            self, data: Union[str, DataFrame, List[Dict]],
            menu_path: str,
            x: str,
            order: Optional[int] = None, rows_size: Optional[int] = 3, cols_size: int = 12,
            padding: Optional[str] = None,
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            show_values: Optional[List] = None,
            calculate_percentages: bool = False,
    ):
        """Create a stacked barchart
        """
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        value_columns = [col for col in df.columns if col != x]
        if calculate_percentages:
            df[value_columns] = df[value_columns].apply(
                lambda row: self._calculate_percentages_from_list(row, 2), axis=1)

        if not option_modifications:
            option_modifications = {
                'subtitle': subtitle if subtitle else '',
                'legend': {
                    'show': True,
                    'type': 'scroll',
                    'itemGap': 16,
                    'icon': 'circle'
                },
                'tooltip': {
                    'trigger': 'item',
                    'axisPointer': {'type': 'cross'},
                },
                'toolbox': self._default_toolbox_options,
                'xAxis': {
                    'name': x_axis_name if x_axis_name else "",
                    'type': 'value',
                    'fontFamily': 'Rubik',
                    'axisLabel': {
                        'formatter': '{value} %' if calculate_percentages else '{value}',
                    }
                },
                'yAxis': {
                    'name': y_axis_name if y_axis_name else "",
                    'type': 'category',
                    'fontFamily': 'Rubik',
                    'nameLocation': 'middle',
                    'nameGap': 35,
                },
                # 'dataZoom': True,
                'grid': {
                    'left': '2%',
                    'right': '2%',
                    'bottom': '10%',
                    'containLabel': True
                },
                'series': [{
                    'type': 'bar',
                    'stack': 'total',
                    'emphasis': {'focus': 'series'},
                    'label': {'show': not show_values or name in show_values},
                    'name': name,
                    'itemStyle': {'borderRadius': [0, 0, 0, 0] if name != value_columns[-1] else [0, 8, 8, 0]},
                } for name in value_columns],
            }

        if 'sort_values' not in df.columns:
            df['sort_values'] = range(len(df))
        return self.free_echarts(
            menu_path=menu_path,
            data=df,
            options=option_modifications,
            order=order,
            rows_size=rows_size,
            cols_size=cols_size,
            padding=padding,
            filters=filters,
            bentobox_data=bentobox_data,
            tabs_index=tabs_index,
            sort={
                'field': 'sort_values',
                'direction': 'asc',
            }

        )

    @logging_before_and_after(logging_level=logger.info)
    def stacked_area_chart(
            self, data: Union[str, DataFrame, List[Dict]],
            menu_path: str,
            x: str,
            order: Optional[int] = None, rows_size: Optional[int] = 3, cols_size: int = 12,
            padding: Optional[str] = None,
            subtitle: Optional[str] = None,
            x_axis_name: Optional[str] = None,
            y_axis_name: Optional[str] = None,
            option_modifications: Optional[Dict] = None,  # third layer
            filters: Optional[Dict] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
            show_values: Optional[List] = None,
            calculate_percentages: bool = False,
    ):
        """Create a stacked barchart
        """
        df: DataFrame = self._plot_aux.validate_data_is_pandarable(data)
        value_columns = [col for col in df.columns if col != x]
        if calculate_percentages:
            df[value_columns] = df[value_columns].apply(
                lambda row: self._calculate_percentages_from_list(row, 2), axis=1)

        if not option_modifications:
            option_modifications = {
                'subtitle': subtitle if subtitle else '',
                'legend': {
                    'show': True,
                    'type': 'scroll',
                    'icon': 'circle'
                },
                'tooltip': {
                    'trigger': 'item',
                    'axisPointer': {'type': 'cross'},
                },
                'toolbox': self._default_toolbox_options,
                'xAxis': {
                    'type': 'category',
                    'fontFamily': 'Rubik',
                    'name': x_axis_name if x_axis_name else "",
                    'nameLocation': 'middle',
                    'boundaryGap': False,
                },
                'yAxis': {
                    'name': y_axis_name if y_axis_name else "",
                    'type': 'value',
                    'fontFamily': 'Rubik',
                    'axisLabel': {
                        'formatter': '{value} %' if calculate_percentages else '{value}',
                    }
                },
                # 'dataZoom': True,
                'grid': {
                    'left': '2%',
                    'right': '2%',
                    'bottom': '10%',
                    'containLabel': True
                },
                'series': [{
                    'type': 'line',
                    'stack': 'total',
                    'emphasis': {'focus': 'series'},
                    'label': {'show': not show_values or name in show_values},
                    'areaStyle': {},
                    'name': name,
                    'itemStyle': {'borderRadius': [0, 0, 0, 0] if name != value_columns[-1] else [8, 8, 0, 0]},
                } for name in value_columns],
            }

        if 'sort_values' not in df.columns:
            df['sort_values'] = range(len(df))

        return self.free_echarts(
            menu_path=menu_path,
            data=df,
            options=option_modifications,
            order=order,
            rows_size=rows_size,
            cols_size=cols_size,
            padding=padding,
            filters=filters,
            bentobox_data=bentobox_data,
            tabs_index=tabs_index,
            sort={
                'field': 'sort_values',
                'direction': 'asc',
            }
        )

    @async_auto_call_manager()
    @logging_before_and_after(logging_level=logger.info)
    async def input_form(
            self, report_dataset_properties: Dict, menu_path: str,
            data: Optional[Union[str, DataFrame, List[Dict]]] = None,
            order: Optional[int] = None,
            rows_size: Optional[int] = 3, cols_size: int = 12,
            padding: Optional[str] = None,
            bentobox_data: Optional[Dict] = None,
            tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """
        :param data:
        :param menu_path:
        :param order:
        :param rows_size:
        :param cols_size:
        :param padding:
        :param bentobox_data:
        :param tabs_index:
        """
        self._plot_aux.validate_input_form_data(report_dataset_properties)

        if data is None:
            data = {}
            for fields in report_dataset_properties['fields']:
                for field in fields['fields']:
                    field_name: str = field['fieldName']
                    input_type: Optional[str] = field.get('inputType')
                    if input_type == 'text':
                        data[field_name] = ''
                    if input_type == 'color':
                        data[field_name] = '#000000'
                    elif input_type == 'tel':
                        data[field_name] = ''  # 633668396
                    elif input_type == 'email':
                        data[field_name] = ''  # 'ceo@acme.com'
                    elif input_type == 'password':
                        data[field_name] = ''  # '1234'
                    elif input_type == 'date':
                        data[field_name] = ''  # '1988-01-30',
                    elif input_type == 'dateRange':
                        data[field_name] = ''  # '2018-01-01,2020-01-01'
                    elif input_type == 'datetimeLocal':
                        data[field_name] = ''  # '2022-07-08T15:11'
                    elif input_type == 'month':
                        data[field_name] = ''  # '2019-11'
                    elif input_type == 'week':
                        data[field_name] = ''  # '2022W12'
                    elif input_type == 'url':
                        data[field_name] = ''  # 'www.shimoku.com'
                    elif input_type == 'time':
                        data[field_name] = ''  # '00:00'
                    elif input_type == 'range':
                        data[field_name] = ''  # data[options][0]
                    elif input_type == 'select':
                        data[field_name] = ''  # data['options'][0]
                    elif input_type == 'multiSelect':
                        data[field_name] = ''  # data['options'][0]
                    elif input_type == 'checkbox':
                        data[field_name] = ''  # data['options'][0]
                    elif input_type == 'radio':
                        data[field_name] = ''  # data['options'][0]
                    elif input_type == 'number':
                        data[field_name] = 0
                    else:
                        data[field_name] = ''  # default is text

        # TODO y esto tambien lo podría usar el método free_echarts!!
        return await self._create_dataset_charts(
            report_dataset_properties=report_dataset_properties,
            options={},
            report_type='FORM',
            menu_path=menu_path, order=order,
            rows_size=rows_size, cols_size=cols_size, padding=padding,
            data=data, bentobox_data=bentobox_data,
            force_custom_field=True,
            tabs_index=tabs_index
        )

    @logging_before_and_after(logging_level=logger.info)
    def generate_input_form_groups(
        self, menu_path: str, order: int,
        form_groups: Dict, dynamic_sequential_show: Optional[bool] = False,
        next_group_label: Optional[str] = 'Next',
        rows_size: Optional[int] = 3, cols_size: int = 12,
        padding: Optional[str] = None,
        bentobox_data: Optional[Dict] = None,
        tabs_index: Optional[Tuple[str, str]] = None,
    ):
        """
        :param dynamic_sequential_show:
        :param next_group_label:
        :param form_groups:
        :param menu_path:
        :param order:
        :param rows_size:
        :param cols_size:
        :param padding:
        :param bentobox_data:
        :param tabs_index:
        """

        report_dataset_properties = {'fields': []}
        next_id = str(uuid.uuid1()) if dynamic_sequential_show else None

        for form_group_name, form_group in form_groups.items():
            form_group_json = {'title': form_group_name, 'fields': form_group}
            if next_id:
                form_group_json['id'] = next_id
                next_id = str(uuid.uuid1())
                form_group_json['nextFormGroup'] = {'id': next_id, 'label': next_group_label}
            report_dataset_properties['fields'] += [form_group_json]

        if next_id:
            del report_dataset_properties['fields'][-1]['nextFormGroup']

        self.input_form(
            report_dataset_properties=report_dataset_properties,
            menu_path=menu_path, order=order, rows_size=rows_size, cols_size=cols_size,
            padding=padding, bentobox_data=bentobox_data, tabs_index=tabs_index
        )
